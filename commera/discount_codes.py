import frappe
from frappe import _
from frappe.utils.data import cstr, flt

from commera.commera_ecommerce.doctype.commera_discount.commera_discount import (
	ORDER,
	PRODUCT,
	CommeraDiscount,
	DiscountCodeError,
	get_code_name,
)

MAX_DISCOUNT_CODES = 5


def get_discount_codes(doc) -> list[str]:
	"""The Commera Discount codes a cart, Quotation or Sales Order holds, in the order they were applied."""
	fieldname = "discount_codes" if doc.doctype == "Commera Cart" else "custom_discount_codes"
	return [code for code in cstr(doc.get(fieldname)).splitlines() if code.strip()]


def get_discount(code: str) -> CommeraDiscount:
	return frappe.get_cached_doc("Commera Discount", code)


def validate_new_discount_code(code: str, codes: list[str]) -> str:
	"""Check that a shopper's code can join the codes already applied, and return its stored name."""
	code = get_code_name(code)
	if not frappe.db.exists("Commera Discount", code):
		frappe.throw(_("{0} is not a valid discount code.").format(code), DiscountCodeError)
	if code in codes:
		frappe.throw(_("{0} is already applied.").format(code), DiscountCodeError)
	if len(codes) >= MAX_DISCOUNT_CODES:
		frappe.throw(
			_("A cart holds at most {0} discount codes.").format(MAX_DISCOUNT_CODES), DiscountCodeError
		)

	discount = get_discount(code)
	discount.validate_usable()
	for applied_code in codes:
		if not discount.can_combine_with(get_discount(applied_code)):
			frappe.throw(_("{0} cannot be combined with {1}.").format(code, applied_code), DiscountCodeError)
	return code


def remove_code_discounts(doc, method=None):
	"""Take the code discounts off before ERPNext prices the document again, so they never apply twice.
	Clamped at zero: other code may already have reset these fields."""
	for item in doc.items:
		if flt(item.get("custom_code_discount")):
			item.discount_amount = max(flt(item.discount_amount) - flt(item.custom_code_discount), 0)
			item.rate = (flt(item.rate_with_margin) or flt(item.price_list_rate)) - item.discount_amount
		item.custom_code_discount = 0
		item.custom_discount_code = None

	if flt(doc.get("custom_code_order_discount")):
		doc.discount_amount = max(flt(doc.discount_amount) - flt(doc.custom_code_order_discount), 0)
	doc.custom_code_order_discount = 0


def apply_code_discounts(doc, method=None):
	"""Add the discount codes on top of ERPNext's price: product codes per line, then order codes on the
	discounted subtotal. The best product code wins on each line."""
	discounts = [get_discount(code) for code in get_discount_codes(doc)]
	discounts = [discount for discount in discounts if discount.is_for_currency(doc.currency)]
	if not discounts:
		return

	product_discounts = [discount for discount in discounts if discount.discount_class == PRODUCT]
	for item in doc.items:
		apply_line_discount(item, product_discounts)
	doc.calculate_taxes_and_totals()

	apply_order_discount(doc, [discount for discount in discounts if discount.discount_class == ORDER])
	doc.calculate_taxes_and_totals()


def apply_line_discount(item, product_discounts: list[CommeraDiscount]):
	rate = flt(item.rate)
	best_code, best_discount = None, 0.0
	for discount in product_discounts:
		unit_discount = discount.get_unit_discount(rate) if discount.is_for_line(item) else 0
		if unit_discount > best_discount:
			best_code, best_discount = discount.name, unit_discount
	if not best_code:
		return

	best_discount = flt(best_discount, item.precision("discount_amount"))
	# ERPNext rebuilds a percentage discount from the price list, which would drop the code's share.
	item.discount_percentage = 0
	item.discount_amount = flt(item.discount_amount) + best_discount
	item.rate = rate - best_discount
	item.custom_code_discount = best_discount
	item.custom_discount_code = best_code


def apply_order_discount(doc, order_discounts: list[CommeraDiscount]):
	subtotal = flt(doc.total)
	amount = sum(discount.get_order_discount(subtotal) for discount in order_discounts)
	amount = flt(min(amount, subtotal), doc.precision("discount_amount"))
	if not amount:
		return

	# Like Shopify, an order code comes off the subtotal, before tax and shipping.
	if not flt(doc.discount_amount):
		doc.apply_discount_on = "Net Total"
	# ERPNext's own percentage discount is kept as an amount, so the code's share can be added to it.
	doc.discount_amount = flt(doc.discount_amount) + amount
	doc.additional_discount_percentage = 0
	doc.custom_code_order_discount = amount


def count_code_uses(doc, method=None):
	for code in get_discount_codes(doc):
		get_discount(code).count_use(1)


def uncount_code_uses(doc, method=None):
	for code in get_discount_codes(doc):
		get_discount(code).count_use(-1)
