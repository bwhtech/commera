# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

from collections import Counter

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Count, Sum
from frappe.utils.data import cint, cstr, date_diff, flt, formatdate

from commera.api.admin.analytics import (
	build_month_buckets,
	month_key,
	month_window,
)
from commera.api.admin.catalog import get_item_templates_by_item_code
from commera.api.admin.orders import (
	describe_payment_state,
	describe_state,
	is_webshop_order,
	read_order_lifecycles,
	read_paid_orders,
)
from commera.utils import get_item_images

PAGE_LENGTH = 20

TOP_PRODUCT_LIMIT = 5

SPEND_CHART_MONTHS = 12

ADDRESS_LINE_FIELDS = (
	"address_line1",
	"address_line2",
	"city",
	"state",
	"pincode",
	"country",
)

# Caps the IN lists the batched address/order reads build from a page.
MAX_PAGE_LENGTH = 100

# How many of a customer's own orders the profile screen's "Recent orders" list shows. A customer
# in this seed data has at most a handful, but a long-lived real customer should not blow this open.
CUSTOMER_ORDER_LIMIT = 50


@frappe.whitelist()
def get_customers(search: str | None = None, start: int = 0, page_length: int = PAGE_LENGTH):
	"""The whole Customers screen in one call."""
	frappe.has_permission("Customer", ptype="read", throw=True)

	# Or-ed against nothing else here (there are no tab filters, unlike Orders), so a plain
	# or_filters list is enough — see orders.get_orders for why it can't just be appended.
	or_filters = (
		[
			["name", "like", f"%{search}%"],
			["customer_name", "like", f"%{search}%"],
			["email_id", "like", f"%{search}%"],
		]
		if search
		else None
	)

	if or_filters:
		total = len(frappe.get_all("Customer", or_filters=or_filters, pluck="name"))
	else:
		total = frappe.db.count("Customer")

	customers = frappe.get_all(
		"Customer",
		or_filters=or_filters,
		fields=["name", "customer_name", "email_id", "creation"],
		order_by="creation desc",
		start=cint(start),
		page_length=min(cint(page_length) or PAGE_LENGTH, MAX_PAGE_LENGTH),
	)
	if not customers:
		return {"customers": [], "total": total}

	customer_names = [row.name for row in customers]
	stats = read_customer_order_stats(customer_names)
	addresses = read_customer_addresses(customer_names)

	return {
		"customers": [
			{
				"id": row.name,
				"name": row.customer_name or row.name,
				"email": row.email_id,
				"city": addresses.get(row.name, {}).get("city"),
				"orders": cint(stats.get(row.name, {}).get("order_count")),
				"spend": flt(stats.get(row.name, {}).get("spend")),
				"since": row.creation,
			}
			for row in customers
		],
		"total": total,
	}


def read_customer_order_stats(customer_names: list) -> dict:
	"""Lifetime order count and spend for a whole page of customers, in one query. Counts drafts as real
	revenue and sums base_grand_total rather than grand_total, both the way orders.read_sales_window does."""
	if not customer_names:
		return {}
	sales_order = frappe.qb.DocType("Sales Order")
	rows = (
		frappe.qb.from_(sales_order)
		.select(
			sales_order.customer,
			Count(sales_order.name).as_("order_count"),
			Sum(sales_order.base_grand_total).as_("spend"),
		)
		.where(is_webshop_order(sales_order))
		.where(sales_order.customer.isin(customer_names))
		.groupby(sales_order.customer)
	).run(as_dict=True)
	return {row.customer: row for row in rows}


def read_customer_addresses(customer_names: list) -> dict:
	if not customer_names:
		return {}

	address_names_by_customer: dict = {}
	for row in frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Address", "link_doctype": "Customer", "link_name": ["in", customer_names]},
		fields=["parent", "link_name"],
	):
		address_names_by_customer.setdefault(row.link_name, []).append(row.parent)

	address_names = [name for names in address_names_by_customer.values() for name in names]
	if not address_names:
		return {}

	address_by_name = {
		row.name: row
		for row in frappe.get_all(
			"Address",
			filters={"name": ["in", address_names]},
			fields=["name", "is_primary_address", *ADDRESS_LINE_FIELDS],
		)
	}

	addresses = {}
	for customer, names in address_names_by_customer.items():
		rows = [address_by_name[name] for name in names if name in address_by_name]
		rows.sort(key=lambda row: not cint(row.is_primary_address))
		if not rows:
			continue
		addresses[customer] = {
			"city": next((row.city for row in rows if row.city), None),
			"address": format_address(rows[0]),
		}
	return addresses


def format_address(address) -> str | None:
	lines = [cstr(address.get(fieldname)).strip() for fieldname in ADDRESS_LINE_FIELDS]
	return "\n".join(line for line in lines if line) or None


@frappe.whitelist()
def get_customer(customer: str):
	"""Everything one customer's profile screen needs, in one call."""
	frappe.has_permission("Customer", doc=customer, ptype="read", throw=True)

	doc = frappe.db.get_value(
		"Customer",
		customer,
		["name", "customer_name", "email_id", "mobile_no", "creation", "customer_details"],
		as_dict=True,
	)
	if not doc:
		frappe.throw(_("Customer {0} not found").format(customer))

	lifetime_orders = read_customer_lifetime_orders(customer)
	order_count = len(lifetime_orders)
	spend = sum(flt(row.base_grand_total) for row in lifetime_orders)

	first_order = lifetime_orders[0] if lifetime_orders else None
	last_order = lifetime_orders[-1] if lifetime_orders else None

	items = read_customer_items(customer)
	address = read_customer_addresses([doc.name]).get(doc.name, {})
	payment_modes = Counter(
		row.custom_ecommerce_payment_mode for row in lifetime_orders if row.custom_ecommerce_payment_mode
	)
	discount_uses = read_customer_discount_uses(customer)

	return {
		"id": doc.name,
		"name": doc.customer_name or doc.name,
		"email": doc.email_id,
		"phone": doc.mobile_no,
		"city": address.get("city"),
		"address": address.get("address"),
		"since": doc.creation,
		"orders": order_count,
		"spend": spend,
		"average_order": flt(spend / order_count) if order_count else 0,
		"first_order": first_order.transaction_date if first_order else None,
		"last_order": last_order.transaction_date if last_order else None,
		"days_between_orders": get_days_between_orders(lifetime_orders),
		"units": sum(flt(row.units) for row in items),
		"payment_mode": payment_modes.most_common(1)[0][0] if payment_modes else None,
		"acquisition": get_acquisition(first_order.name if first_order else None),
		"top_products": get_top_products(items),
		"spend_by_month": get_spend_by_month(lifetime_orders),
		"note": cstr(doc.customer_details),
		"discount_uses": discount_uses,
		"discount_saved": sum(flt(use.amount) for use in discount_uses),
		"recent_orders": [
			{key: value for key, value in order.items() if key != "base_total"}
			for order in read_customer_orders(customer)
		],
	}


@frappe.whitelist(methods=["POST"])
def save_customer_note(customer: str, note: str):
	frappe.has_permission("Customer", doc=customer, ptype="write", throw=True)

	doc = frappe.get_doc("Customer", cstr(customer))
	doc.customer_details = cstr(note)
	doc.save()
	return doc.customer_details


def read_customer_lifetime_orders(customer: str) -> list:
	sales_order = frappe.qb.DocType("Sales Order")
	return (
		frappe.qb.from_(sales_order)
		.select(
			sales_order.name,
			sales_order.transaction_date,
			sales_order.base_grand_total,
			sales_order.custom_ecommerce_payment_mode,
		)
		.where(is_webshop_order(sales_order))
		.where(sales_order.customer == customer)
		.orderby(sales_order.transaction_date)
		.orderby(sales_order.creation)
	).run(as_dict=True)


def read_customer_items(customer: str) -> list:
	sales_order = frappe.qb.DocType("Sales Order")
	sales_order_item = frappe.qb.DocType("Sales Order Item")
	rows = (
		frappe.qb.from_(sales_order_item)
		.join(sales_order)
		.on(sales_order_item.parent == sales_order.name)
		.select(
			sales_order_item.item_code,
			Sum(sales_order_item.qty).as_("units"),
			Sum(sales_order_item.base_amount).as_("spend"),
		)
		.where(is_webshop_order(sales_order))
		.where(sales_order.customer == customer)
		.groupby(sales_order_item.item_code)
	).run(as_dict=True)
	rows.sort(key=lambda row: (-flt(row.units), cstr(row.item_code)))
	return rows


def get_top_products(items: list) -> list:
	items = items[:TOP_PRODUCT_LIMIT]
	if not items:
		return []

	item_codes = [row.item_code for row in items]
	item_by_code = {
		row.name: row
		for row in frappe.get_all(
			"Item",
			filters={"name": ["in", item_codes]},
			fields=["name", "item_name", "variant_of"],
		)
	}
	template_by_code = get_item_templates_by_item_code(item_codes)
	image_by_item_code = get_item_images(item_codes)

	return [
		{
			"item_code": row.item_code,
			"product": template_by_code.get(row.item_code)
			or item_by_code.get(row.item_code, {}).get("variant_of")
			or row.item_code,
			"name": item_by_code.get(row.item_code, {}).get("item_name") or row.item_code,
			"units": flt(row.units),
			"spend": flt(row.spend),
			"image": image_by_item_code.get(row.item_code),
		}
		for row in items
	]


def get_days_between_orders(lifetime_orders: list) -> int | None:
	if len(lifetime_orders) < 2:
		return None
	span = date_diff(lifetime_orders[-1].transaction_date, lifetime_orders[0].transaction_date)
	return cint(span / (len(lifetime_orders) - 1))


def get_spend_by_month(lifetime_orders: list) -> list:
	start, today, _months = month_window(SPEND_CHART_MONTHS)
	spend_by_key = dict.fromkeys(build_month_buckets(start, today), 0.0)

	for row in lifetime_orders:
		key = month_key(row.transaction_date)
		if key in spend_by_key:
			spend_by_key[key] += flt(row.base_grand_total)

	return [
		{"label": formatdate(f"{key}-01", "MMM"), "spend": spend_by_key[key]} for key in sorted(spend_by_key)
	]


def get_acquisition(first_order: str | None) -> dict | None:
	if not first_order:
		return None

	event = frappe.get_all(
		"Storefront Analytics Event",
		filters={"order_id": first_order},
		fields=["utm_source", "utm_campaign"],
		order_by="creation asc",
		limit=1,
	)
	if not event or not event[0].utm_source:
		return None
	return {"source": event[0].utm_source, "campaign": event[0].utm_campaign or None}


def read_customer_discount_uses(customer: str) -> list:
	use = frappe.qb.DocType("Commera Discount Use")
	discount = frappe.qb.DocType("Commera Discount")
	return (
		frappe.qb.from_(use)
		.left_join(discount)
		.on(discount.name == use.discount)
		.select(
			use.sales_order,
			use.code,
			use.base_amount.as_("amount"),
			use.creation.as_("used_on"),
			discount.title,
		)
		.where(use.customer == customer)
		.orderby(use.creation, order=Order.desc)
	).run(as_dict=True)


def read_customer_orders(customer: str) -> list:
	"""This one customer's own order history, in the same shape orders.get_orders uses for its rows.
	Counts drafts, for the reason read_customer_order_stats gives."""
	orders = frappe.get_all(
		"Sales Order",
		filters=[
			["customer", "=", customer],
			["docstatus", "<", 2],
			["order_type", "=", "Shopping Cart"],
		],
		fields=[
			"name",
			"transaction_date",
			"status",
			"grand_total",
			"base_grand_total",
			"currency",
			"docstatus",
			"per_delivered",
			"custom_ecommerce_payment_mode",
		],
		order_by="creation desc",
		page_length=CUSTOMER_ORDER_LIMIT,
	)
	if not orders:
		return []

	order_names = [row.name for row in orders]
	item_counts: dict = {}
	for row in frappe.get_all(
		"Sales Order Item", filters={"parent": ["in", order_names]}, fields=["parent", "qty"]
	):
		item_counts[row.parent] = item_counts.get(row.parent, 0) + flt(row.qty)

	lifecycles = read_order_lifecycles(order_names)
	paid_orders = read_paid_orders(order_names)

	return [
		{
			"name": row.name,
			"placed_on": row.transaction_date,
			"status": row.status,
			"state": describe_state(row, lifecycles.get(cstr(row.name))),
			"payment_state": describe_payment_state(row, paid_orders),
			"total": flt(row.grand_total),
			"base_total": flt(row.base_grand_total),
			"currency": row.currency,
			"item_count": item_counts.get(row.name, 0),
		}
		for row in orders
	]
