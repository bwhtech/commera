"""`store_milestone_reached`: each step of the activation funnel, read off the database as it changes.

Nothing records that a milestone was sent. Each fires when its own count reaches the step, so the data stays the one owner of the fact.
"""

import frappe

from commera import setup_state
from commera.api.admin import payments as admin_payments
from commera.core import is_cod
from commera.plugin_events import get_settled_orders_query
from commera.sdk import STORE_ORDER_TYPE
from commera.telemetry import (
	OTHER,
	capture,
	days_since_install,
	get_source,
	registry_value,
	telemetry_event,
)

COD = "cod"
TENTH_PAID_ORDER = 10
CHECKOUT_REFERENCE = "Quotation"


def reach(milestone: str, **props):
	capture(
		"store_milestone_reached",
		milestone=milestone,
		days_since_install=days_since_install(),
		source=get_source(),
		**props,
	)


def has_exactly_one(doctype: str, filters: dict) -> bool:
	"""Whether a just-made record is the first: reads at most two rows, so a busy store pays no count."""
	return len(frappe.get_all(doctype, filters=filters, pluck="name", limit=2)) == 1


def get_payment_method(payment_mode: str | None) -> str:
	"""A gateway slug from the registry, `cod`, or `other` for a gateway the registry does not list."""
	if is_cod(payment_mode):
		return COD
	slugs = {gateway["label"].casefold(): gateway["slug"] for gateway in admin_payments.PAYMENT_GATEWAYS}
	return slugs.get((payment_mode or "").strip().casefold(), OTHER)


@telemetry_event
def on_product_insert(doc, method=None):
	if setup_state.count_products() == 1:
		reach("first_product_created")


@telemetry_event
def on_variant_update(doc, method=None):
	if not doc.is_published or not doc.has_value_changed("is_published"):
		return
	if setup_state.count_published_products() == 1:
		reach("first_product_published")


@telemetry_event
def payment_method_enabled(payment_method: str):
	"""Called after a gateway or cash on delivery is switched on."""
	if setup_state.count_payment_methods() == 1:
		reach("payment_method_enabled", payment_method=registry_value(payment_method, get_payment_methods()))


@telemetry_event
def get_cod_state() -> bool:
	"""Read before a save that can switch cash on delivery, for `cod_saved`."""
	return setup_state.is_cod_enabled()


@telemetry_event
def cod_saved(was_enabled: bool | None):
	if was_enabled is False and setup_state.is_cod_enabled():
		payment_method_enabled(COD)


def get_payment_methods() -> tuple:
	return (*(gateway["slug"] for gateway in admin_payments.PAYMENT_GATEWAYS), COD)


@telemetry_event
def on_shipping_rule_insert(doc, method=None):
	if doc.shipping_rule_type == setup_state.STORE_SHIPPING_RULES["shipping_rule_type"]:
		shipping_method_added()


@telemetry_event
def shipping_method_added():
	"""Called after a selling shipping rule is made or a carrier is switched on."""
	if setup_state.count_shipping_methods() == 1:
		reach("shipping_configured")


@telemetry_event
def get_theme_state() -> bool:
	"""Read before a theme save, for `theme_saved`."""
	return setup_state.is_theme_customized()


@telemetry_event
def theme_saved(was_customized: bool | None):
	if was_customized is False and setup_state.is_theme_customized():
		reach("theme_customized")


@telemetry_event
def on_gateway_payment_request_insert(doc, method=None):
	if doc.ref_doctype != CHECKOUT_REFERENCE:
		return
	if has_exactly_one("Gateway Payment Request", {"ref_doctype": CHECKOUT_REFERENCE}):
		reach("first_gateway_checkout", payment_method=get_payment_method(doc.gateway))


@telemetry_event
def on_commera_event_insert(doc, method=None):
	"""`order_placed` and `order_paid` are recorded once per order, whichever path placed or paid it."""
	if doc.reference_doctype != "Sales Order":
		return
	if doc.event == "order_placed":
		order_placed(doc.reference_name)
	elif doc.event == "order_paid":
		order_paid(doc.reference_name)


def order_placed(sales_order: str):
	if has_exactly_one("Sales Order", {"order_type": STORE_ORDER_TYPE, "docstatus": 1}):
		payment_mode = frappe.db.get_value("Sales Order", sales_order, "custom_ecommerce_payment_mode")
		reach(
			"first_order_placed",
			payment_method=get_payment_method(payment_mode),
			is_guest=is_guest_order(sales_order),
		)


def order_paid(sales_order: str):
	paid_orders = len(get_settled_orders_query().limit(TENTH_PAID_ORDER + 1).run())
	if paid_orders == 1:
		payment_mode = frappe.db.get_value("Sales Order", sales_order, "custom_ecommerce_payment_mode")
		reach(
			"first_order_paid",
			payment_method=get_payment_method(payment_mode),
			is_guest=is_guest_order(sales_order),
		)
	elif paid_orders == TENTH_PAID_ORDER:
		reach("tenth_order_paid")


def is_guest_order(sales_order: str) -> bool:
	"""A guest order comes from a cart that carries a guest cart key."""
	cart = frappe.db.get_value(
		"Sales Order Item", {"parent": sales_order, "parenttype": "Sales Order"}, "prevdoc_docname"
	)
	return bool(cart and frappe.db.get_value("Quotation", cart, "custom_guest_cart_key"))
