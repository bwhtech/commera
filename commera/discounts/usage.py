import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils.data import cint, flt

from commera.core import latest_committed_reads
from commera.discounts.allocations import get_allocations
from commera.discounts.cart_context import get_cart_context
from commera.plugin_events import fire_event


class DiscountLimitError(frappe.ValidationError):
	pass


def has_used_before(
	discount: str, cart, excluded_orders: list[str] | None = None, for_update: bool = False
) -> bool:
	use = frappe.qb.DocType("Commera Discount Use")
	identity = None
	for field, value in (("customer", cart.customer), ("email", cart.email), ("phone", cart.phone)):
		if value:
			identity = (use[field] == value) if identity is None else identity | (use[field] == value)
	if identity is None:
		return False
	query = frappe.qb.from_(use).select(use.name).where((use.discount == discount) & identity).limit(1)
	if excluded_orders:
		query = query.where(use.sales_order.notin(excluded_orders))
	if for_update:
		query = query.for_update()
	return bool(query.run())


def is_first_order(cart) -> bool:
	# Draft orders count: cash on delivery stays draft.
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


def get_earlier_orders(sales_order) -> list[str]:
	orders = []
	name = sales_order.amended_from
	while name:
		orders.append(name)
		name = frappe.db.get_value("Sales Order", name, "amended_from")
	return orders


def record_discount_uses(sales_order, method=None):
	# A use counts from placement; cancel, amend, bill, return or delete never changes it.
	amounts = {}
	for allocation in get_allocations(sales_order):
		key = (allocation["discount"], allocation.get("code"))
		amounts[key] = amounts.get(key, 0) + flt(allocation["amount"])
	if not amounts:
		return

	# An amended order is the same placement as the order it replaces, so it keeps that order's uses.
	earlier_orders = get_earlier_orders(sales_order) if sales_order.amended_from else []
	conversion_rate = flt(sales_order.conversion_rate) or 1
	base_amounts = {}
	for (discount, _code), amount in amounts.items():
		base_amounts[discount] = base_amounts.get(discount, 0) + flt(amount * conversion_rate, 2)
	validate_discount_limits(sales_order, amounts, base_amounts, earlier_orders)
	if earlier_orders and frappe.db.exists("Commera Discount Use", {"sales_order": ["in", earlier_orders]}):
		return

	for (discount, code), amount in amounts.items():
		frappe.get_doc(
			{
				"doctype": "Commera Discount Use",
				"discount": discount,
				"code": code,
				"sales_order": sales_order.name,
				"amount": amount,
				"order_total": flt(sales_order.grand_total),
				"base_amount": flt(amount * conversion_rate, 2),
				"base_order_total": flt(sales_order.base_grand_total),
				"customer": sales_order.customer,
				"email": (sales_order.contact_email or "").lower() or None,
				"phone": sales_order.contact_mobile or sales_order.contact_phone or None,
			}
		).insert(ignore_permissions=True)
	add_usage(base_amounts, {code for _discount, code in amounts if code}, flt(sales_order.base_grand_total))
	for (discount, code), amount in amounts.items():
		fire_event(
			"discount_used",
			"Sales Order",
			sales_order.name,
			data={"discount": discount, "code": code, "amount": amount},
			key=f"{discount}-{code or ''}",
		)


@latest_committed_reads()
def validate_discount_limits(sales_order, amounts: dict, base_amounts: dict, earlier_orders: list[str]):
	# A locking read waits for a concurrent placement and sees its commit; a plain read would not (REPEATABLE READ).
	cart = get_cart_context(sales_order)
	labels = {discount: code for discount, code in amounts}
	for discount_name in sorted(base_amounts):
		counters = frappe.db.get_value(
			"Commera Discount", discount_name, ["times_used", "discount_given"], as_dict=True, for_update=True
		)
		discount = frappe.get_cached_doc("Commera Discount", discount_name)
		label = labels[discount_name] or discount.title
		earlier_uses, earlier_amount = get_earlier_usage({"discount": discount_name}, earlier_orders)
		if discount.usage_limit and cint(counters.times_used) - earlier_uses >= cint(discount.usage_limit):
			frappe.throw(_("{0} has been used up by other orders.").format(label), DiscountLimitError)
		if flt(discount.budget):
			budget = flt(discount.budget) * discount.get_company_exchange_rate()
			given = flt(counters.discount_given) - earlier_amount + base_amounts[discount_name]
			if flt(given, 2) > flt(budget, 2):
				frappe.throw(_("{0} has run out of budget.").format(label), DiscountLimitError)
		if discount.once_per_customer and has_used_before(
			discount_name, cart, earlier_orders, for_update=True
		):
			frappe.throw(
				_("This customer has already used {0} on another order.").format(label), DiscountLimitError
			)

	for code in sorted(code for _discount, code in amounts if code):
		is_generated, times_used = frappe.db.get_value(
			"Commera Discount Code", code, ["is_generated", "times_used"], for_update=True
		)
		if is_generated and cint(times_used) - get_earlier_usage({"code": code}, earlier_orders)[0] > 0:
			frappe.throw(
				_("{0} is a single-use code and another order has used it.").format(code), DiscountLimitError
			)


def get_earlier_usage(filters: dict, earlier_orders: list[str]) -> tuple[int, float]:
	if not earlier_orders:
		return 0, 0.0
	use = frappe.qb.DocType("Commera Discount Use")
	query = (
		frappe.qb.from_(use)
		.select(Count(use.name), Sum(use.base_amount))
		.where(use.sales_order.isin(earlier_orders))
	)
	for field, value in filters.items():
		query = query.where(use[field] == value)
	count, amount = query.run()[0]
	return cint(count), flt(amount)


@latest_committed_reads()
def add_usage(base_amounts: dict[str, float], codes: set[str], base_order_total: float):
	# Increments, not recounts: the update reads the latest committed counter, whatever this snapshot holds.
	discount = frappe.qb.DocType("Commera Discount")
	for name, base_amount in base_amounts.items():
		(
			frappe.qb.update(discount)
			.set(discount.times_used, discount.times_used + 1)
			.set(discount.discount_given, discount.discount_given + base_amount)
			.set(discount.sales, discount.sales + base_order_total)
			.where(discount.name == name)
		).run()
		frappe.clear_document_cache("Commera Discount", name)
	code_table = frappe.qb.DocType("Commera Discount Code")
	for code in codes:
		(
			frappe.qb.update(code_table)
			.set(code_table.times_used, code_table.times_used + 1)
			.where(code_table.name == code)
		).run()
		frappe.clear_document_cache("Commera Discount Code", code)
