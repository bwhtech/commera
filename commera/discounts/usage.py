import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils.data import cint, flt

from commera.discounts.allocations import get_allocations
from commera.discounts.cart_context import get_cart_context
from commera.plugin_events import fire_event


def has_used_before(discount: str, cart, excluded_orders: list[str] | None = None) -> bool:
	identities = {"customer": cart.customer, "email": cart.email, "phone": cart.phone}
	or_filters = {field: value for field, value in identities.items() if value}
	if not or_filters:
		return False
	filters = {"discount": discount}
	if excluded_orders:
		filters["sales_order"] = ["not in", excluded_orders]
	return bool(frappe.get_all("Commera Discount Use", filters=filters, or_filters=or_filters, limit=1))


def is_first_order(cart) -> bool:
	"""No earlier store order for this customer or email. Draft orders count: cash on delivery stays draft."""
	sales_order = frappe.qb.DocType("Sales Order")
	identity = None
	if cart.customer:
		identity = sales_order.customer == cart.customer
	if cart.email:
		by_email = sales_order.contact_email == cart.email
		identity = by_email if identity is None else identity | by_email
	if identity is None:
		return True
	query = (
		frappe.qb.from_(sales_order)
		.select(sales_order.name)
		.where(identity & (sales_order.docstatus < 2) & (sales_order.order_type == "Shopping Cart"))
		.limit(1)
	)
	if cart.doc.doctype == "Sales Order" and cart.doc.name:
		query = query.where(sales_order.name != cart.doc.name)
	return not query.run()


def validate_amended_discount_uses(sales_order, method=None):
	"""An amended order is the same placement as the order it replaces, so it keeps that order's uses; a code
	that another order used up meanwhile is refused."""
	if not sales_order.amended_from:
		return
	earlier_orders = get_earlier_orders(sales_order)
	cart = get_cart_context(sales_order)
	for discount_name, code in {(row["discount"], row.get("code")) for row in get_allocations(sales_order)}:
		discount = frappe.get_cached_doc("Commera Discount", discount_name)
		label = code or discount.title
		other_uses = {"sales_order": ["not in", earlier_orders]}
		if code and frappe.get_cached_value("Commera Discount Code", code, "is_generated"):
			if frappe.db.exists("Commera Discount Use", {**other_uses, "code": code}):
				frappe.throw(_("{0} is a single-use code and another order has used it.").format(label))
		if discount.once_per_customer and has_used_before(discount_name, cart, earlier_orders):
			frappe.throw(_("This customer has already used {0} on another order.").format(label))
		if discount.usage_limit and frappe.db.count(
			"Commera Discount Use", {**other_uses, "discount": discount_name}
		) >= cint(discount.usage_limit):
			frappe.throw(_("{0} has been used up by other orders.").format(label))


def get_earlier_orders(sales_order) -> list[str]:
	"""The cancelled orders an amended order replaces, most recent first."""
	orders = []
	name = sales_order.amended_from
	while name:
		orders.append(name)
		name = frappe.db.get_value("Sales Order", name, "amended_from")
	return orders


def record_discount_uses(sales_order, method=None):
	"""Log each discount a placed order used. Counts, budgets and once-per-customer read this log. A use
	counts from placement on: cancelling, amending, billing or returning the order never changes it."""
	if sales_order.amended_from and frappe.db.exists(
		"Commera Discount Use", {"sales_order": ["in", get_earlier_orders(sales_order)]}
	):
		return
	amounts = {}
	for allocation in get_allocations(sales_order):
		key = (allocation["discount"], allocation.get("code"))
		amounts[key] = amounts.get(key, 0) + flt(allocation["amount"])

	for (discount, code), amount in amounts.items():
		frappe.get_doc(
			{
				"doctype": "Commera Discount Use",
				"discount": discount,
				"code": code,
				"sales_order": sales_order.name,
				"amount": amount,
				"order_total": flt(sales_order.grand_total),
				"customer": sales_order.customer,
				"email": (sales_order.contact_email or "").lower() or None,
				"phone": sales_order.contact_mobile or sales_order.contact_phone or None,
			}
		).insert(ignore_permissions=True)
	refresh_usage({discount for discount, _code in amounts}, {code for _discount, code in amounts if code})
	for (discount, code), amount in amounts.items():
		fire_event(
			"discount_used",
			"Sales Order",
			sales_order.name,
			data={"discount": discount, "code": code, "amount": amount},
			key=f"{discount}-{code or ''}",
		)


def remove_discount_uses(sales_order, method=None):
	uses = frappe.get_all(
		"Commera Discount Use", filters={"sales_order": sales_order.name}, fields=["name", "discount", "code"]
	)
	for use in uses:
		frappe.delete_doc("Commera Discount Use", use.name, ignore_permissions=True, force=True)
	refresh_usage({use.discount for use in uses}, {use.code for use in uses if use.code})


def refresh_usage(discounts: set[str], codes: set[str]):
	"""Recount from the log, under row locks, so two orders placed at once cannot lose a count."""
	use = frappe.qb.DocType("Commera Discount Use")
	for discount in discounts:
		frappe.db.get_value("Commera Discount", discount, "name", for_update=True)
		times_used, discount_given, sales = (
			frappe.qb.from_(use)
			.select(Count(use.name), Sum(use.amount), Sum(use.order_total))
			.where(use.discount == discount)
		).run()[0]
		frappe.db.set_value(
			"Commera Discount",
			discount,
			{"times_used": times_used, "discount_given": flt(discount_given), "sales": flt(sales)},
			update_modified=False,
		)
		frappe.clear_document_cache("Commera Discount", discount)
	for code in codes:
		times_used = frappe.db.count("Commera Discount Use", {"code": code})
		frappe.db.set_value("Commera Discount Code", code, "times_used", times_used, update_modified=False)
		frappe.clear_document_cache("Commera Discount Code", code)
