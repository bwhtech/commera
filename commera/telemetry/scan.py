"""The daily site profile: what a store holds, not what someone clicked today.

It is the only report from a store nobody opened today, and the denominator for every other event. It reads Commera's own tables, only counts and buckets leave, and nothing runs when telemetry is off.
"""

import hashlib

import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count, Sum
from frappe.utils import add_days, date_diff, getdate
from frappe.utils.telemetry import is_pulse_enabled, site_age
from frappe.utils.telemetry.pulse.client import identify

from commera import setup_state
from commera.api.admin.payments import PAYMENT_GATEWAYS
from commera.core import COD_PAYMENT_MODE
from commera.plugin_events import get_settled_orders_query
from commera.roles import COMMERA_ADMIN, COMMERA_USER
from commera.sdk import STORE_ORDER_TYPE
from commera.telemetry import (
	capture,
	get_country_code,
	get_installed_at,
	rows_bucket,
	share_bucket,
	theme_value,
	value_bucket,
)

WINDOW_DAYS = 30
WEEK_DAYS = 7
STAFF_ROLES = (COMMERA_ADMIN, COMMERA_USER, "System Manager")
TRAFFIC_EVENTS = {
	"product_view_sessions_30d": "view_item",
	"add_to_cart_sessions_30d": "add_to_cart",
	"checkout_sessions_30d": "begin_checkout",
}
IDENTIFY_CACHE_KEY = "commera:telemetry:identify"
STORE_ORDERS = {"order_type": STORE_ORDER_TYPE, "docstatus": 1}


def send_site_profile():
	"""Scheduled daily."""
	if not is_pulse_enabled():
		return
	capture("site_profile", **collect())
	send_team_profile()


def collect() -> dict:
	return {
		**identity(),
		**timeline(),
		**catalogue(),
		**payments(),
		**shipping(),
		**storefront(),
		**features(),
		**traffic(),
		**checkout(),
		**orders(),
		**value(),
		**people(),
	}


def identity() -> dict:
	return {"site_age_days": site_age() or 0, "commera_installed_days_ago": days_since(get_installed_at())}


def timeline() -> dict:
	sales_order = DocType("Sales Order")
	first_paid_order = (
		get_settled_orders_query().select(sales_order.creation).orderby(sales_order.creation).limit(1).run()
	)
	return {
		"first_product_days_ago": days_since(oldest(setup_state.PRODUCT_DOCTYPE)),
		"first_gateway_days_ago": days_since(oldest("Payment Gateway Profile", setup_state.ENABLED)),
		"first_order_days_ago": days_since(oldest("Sales Order", STORE_ORDERS)),
		"first_paid_order_days_ago": days_since(first_paid_order[0][1] if first_paid_order else None),
		"last_order_days_ago": days_since(
			frappe.db.get_value("Sales Order", STORE_ORDERS, "creation", order_by="creation desc")
		),
	}


def catalogue() -> dict:
	item_group = DocType("Item Group")
	return {
		"products": setup_state.count_products(),
		"products_published": setup_state.count_published_products(),
		"variants": frappe.db.count("Style Attribute Variant"),
		# Collections are the leaf Item Groups, as the Collections screen counts them.
		"collections": frappe.qb.from_(item_group)
		.select(Count(item_group.name))
		.where(item_group.rgt == item_group.lft + 1)
		.run()[0][0],
	}


def payments() -> dict:
	enabled = set(frappe.get_all("Payment Gateway Profile", filters=setup_state.ENABLED, pluck="name"))
	return {
		**{f"gateway_{gateway['slug']}": gateway["label"] in enabled for gateway in PAYMENT_GATEWAYS},
		"cod_enabled": setup_state.is_cod_enabled(),
	}


def shipping() -> dict:
	has_pickup_field = frappe.get_meta("Warehouse").has_field("custom_store_pickup")
	return {
		"shipping_rules": setup_state.count_shipping_rules(),
		"shipping_carriers_enabled": setup_state.count_enabled_carriers(),
		"pickup_locations": frappe.db.count("Warehouse", {"custom_store_pickup": 1, "disabled": 0})
		if has_pickup_field
		else 0,
	}


def storefront() -> dict:
	analytics = frappe.get_single("Analytics Settings")
	return {
		"theme": theme_value(setup_state.get_active_theme()),
		"storefront_pages": frappe.db.count("Shop Web Page"),
		"plugins_enabled": frappe.db.count("Commera Storefront App", setup_state.ENABLED),
		"analytics_integrations": int(bool(analytics.enable_ga4))
		+ int(bool(analytics.enable_facebook))
		+ sum(1 for row in analytics.custom_tracking_scripts if row.enabled),
	}


def features() -> dict:
	today = getdate()
	discount = DocType("Commera Discount")
	return {
		"discounts_active": frappe.qb.from_(discount)
		.select(Count(discount.name))
		.where(
			(discount.enabled == 1)
			& (discount.starts_on.isnull() | (discount.starts_on <= today))
			& (discount.ends_on.isnull() | (discount.ends_on >= today))
		)
		.run()[0][0],
		"reviews_30d": frappe.db.count("Product Review", {"creation": (">=", since(WINDOW_DAYS))}),
		"wishlist_items": frappe.db.count("Commera Wishlist Item"),
		"oos_subscriptions": frappe.db.count("OOS Notify Subscription", {"notified": 0}),
		"guest_checkout_enabled": bool(
			frappe.db.get_single_value("Commera Settings", "allow_guest_checkout")
		),
	}


def traffic() -> dict:
	"""Sessions, from the first-party event log the storefront already keeps."""
	event = DocType("Storefront Analytics Event")
	rows = (
		frappe.qb.from_(event)
		.select(event.event, Count(event.session_id).distinct())
		.where(event.creation >= since(WINDOW_DAYS))
		.groupby(event.event)
		.run()
	)
	sessions_by_event = dict(rows)
	all_sessions = (
		frappe.qb.from_(event)
		.select(Count(event.session_id).distinct())
		.where(event.creation >= since(WINDOW_DAYS))
		.run()[0][0]
	)
	return {
		"sessions_30d": all_sessions,
		**{key: sessions_by_event.get(name, 0) for key, name in TRAFFIC_EVENTS.items()},
	}


def checkout() -> dict:
	window = {"creation": (">=", since(WINDOW_DAYS))}
	gateway_requests = {"ref_doctype": "Quotation", **window}
	return {
		"gateway_checkouts_30d": frappe.db.count("Gateway Payment Request", gateway_requests),
		"gateway_orders_paid_30d": frappe.db.count(
			"Gateway Payment Request", {**gateway_requests, "status": "Paid"}
		),
		"orders_cod_30d": frappe.db.count(
			"Sales Order", {**STORE_ORDERS, **window, "custom_ecommerce_payment_mode": COD_PAYMENT_MODE}
		),
		"orders_prepaid_30d": frappe.db.count(
			"Sales Order",
			{**STORE_ORDERS, **window, "custom_ecommerce_payment_mode": ("!=", COD_PAYMENT_MODE)},
		),
	}


def orders() -> dict:
	window = {"creation": (">=", since(WINDOW_DAYS))}
	orders_30d = frappe.db.count("Sales Order", {**STORE_ORDERS, **window})
	return {
		"orders_7d": frappe.db.count("Sales Order", {**STORE_ORDERS, "creation": (">=", since(WEEK_DAYS))}),
		"orders_30d": orders_30d,
		"orders_cancelled_30d": frappe.db.count(
			"Sales Order", {"order_type": STORE_ORDER_TYPE, "docstatus": 2, **window}
		),
		"guest_order_share_bucket": share_bucket(count_guest_orders() / orders_30d) if orders_30d else None,
	}


def count_guest_orders() -> int:
	"""Store orders in the window whose cart was a guest cart."""
	sales_order, order_line, cart = DocType("Sales Order"), DocType("Sales Order Item"), DocType("Quotation")
	return (
		frappe.qb.from_(sales_order)
		.join(order_line)
		.on((order_line.parent == sales_order.name) & (order_line.parenttype == "Sales Order"))
		.join(cart)
		.on(cart.name == order_line.prevdoc_docname)
		.select(Count(sales_order.name).distinct())
		.where(
			(sales_order.order_type == STORE_ORDER_TYPE)
			& (sales_order.docstatus == 1)
			& (sales_order.creation >= since(WINDOW_DAYS))
			& (cart.custom_guest_cart_key != "")
		)
		.run()[0][0]
	)


def value() -> dict:
	"""Order value as bands in the store currency, never an amount."""
	sales_order = DocType("Sales Order")
	total, count = (
		frappe.qb.from_(sales_order)
		.select(Sum(sales_order.base_grand_total), Count(sales_order.name))
		.where(
			(sales_order.order_type == STORE_ORDER_TYPE)
			& (sales_order.docstatus == 1)
			& (sales_order.creation >= since(WINDOW_DAYS))
		)
		.run()[0]
	)
	return {
		"gmv_30d_bucket": value_bucket(total or 0),
		"aov_bucket": value_bucket((total or 0) / count) if count else None,
	}


def people() -> dict:
	staff = set(
		frappe.get_all(
			"Has Role",
			filters={
				"role": ("in", STAFF_ROLES),
				"parenttype": "User",
				"parent": ("not in", ("Administrator",)),
			},
			pluck="parent",
			distinct=True,
		)
	)
	enabled_staff = {"name": ("in", list(staff) or [""]), "enabled": 1, "user_type": "System User"}
	return {
		"staff_users": frappe.db.count("User", enabled_staff),
		"staff_active_30d": frappe.db.count(
			"User", {**enabled_staff, "last_active": (">=", since(WINDOW_DAYS))}
		),
		"customers": frappe.db.count("Customer"),
	}


def send_team_profile():
	"""Upsert the Frappe Cloud team's store facts, only when one changed since the last send."""
	if not frappe.conf.get("fc_team"):
		return
	properties = get_team_properties()
	digest = hashlib.sha256(frappe.as_json(properties).encode()).hexdigest()
	if frappe.cache.get_value(IDENTIFY_CACHE_KEY) == digest:
		return
	identify(properties)
	frappe.cache.set_value(IDENTIFY_CACHE_KEY, digest)


def get_team_properties() -> dict:
	company = frappe.db.get_single_value("Commera Settings", "company")
	country, currency = (
		frappe.db.get_value("Company", company, ["country", "default_currency"]) if company else (None, None)
	)
	return {
		"store_country": get_country_code(country),
		"store_currency": currency,
		"commera_activated": bool(frappe.db.exists("Sales Order", STORE_ORDERS)),
		"catalogue_size_bucket": rows_bucket(setup_state.count_products()),
	}


def oldest(doctype: str, filters: dict | None = None):
	return frappe.db.get_value(doctype, filters or {}, "creation", order_by="creation asc")


def since(days: int):
	return add_days(None, -days)


def days_since(value) -> int | None:
	return date_diff(None, value) if value else None
