from dataclasses import dataclass

import frappe
from frappe import _
from frappe.utils.data import cstr, flt

from commera.discounts.cart_context import get_cart_context
from commera.discounts.codes import get_code_discount, get_discount_code_refusal, normalize_code
from commera.discounts.doctype.commera_discount.commera_discount import (
	CommeraDiscount,
	DiscountCodeError,
)
from commera.discounts.usage import has_used_before, is_first_order

MAX_DISCOUNT_CODES = 5


@dataclass
class Selection:
	discount: CommeraDiscount
	code: str | None = None


def get_discount_codes(doc) -> list[str]:
	fieldname = "discount_codes" if doc.doctype == "Commera Cart" else "custom_discount_codes"
	return [code for code in cstr(doc.get(fieldname)).splitlines() if code.strip()]


def get_discount(name: str) -> CommeraDiscount:
	return frappe.get_cached_doc("Commera Discount", name)


def validate_new_discount_code(code: str, codes: list[str], active_codes: list[str] | None = None) -> str:
	# Only active_codes can refuse it for not combining.
	code = normalize_code(code)
	discount_name = get_code_discount(code)
	if not discount_name:
		frappe.throw(_("{0} is not a valid discount code.").format(code), DiscountCodeError)
	if code in codes:
		frappe.throw(_("{0} is already applied.").format(code), DiscountCodeError)
	if len(codes) >= MAX_DISCOUNT_CODES:
		frappe.throw(
			_("A cart holds at most {0} discount codes.").format(MAX_DISCOUNT_CODES), DiscountCodeError
		)

	if is_single_use_spent(code):
		frappe.throw(_("{0} has already been used.").format(code), DiscountCodeError)
	discount = get_discount(discount_name)
	discount.validate_usable()
	for applied_code in codes:
		applied_name = get_code_discount(applied_code)
		if applied_name == discount_name:
			frappe.throw(
				_("{0} gives the same discount as {1}, which is already applied.").format(code, applied_code),
				DiscountCodeError,
			)
		if active_codes is not None and applied_code not in active_codes:
			continue
		if applied_name and not discount.can_combine_with(get_discount(applied_name)):
			frappe.throw(_("{0} cannot be combined with {1}.").format(code, applied_code), DiscountCodeError)
	return code


def get_unusable_code_reason(doc, code: str) -> str | None:
	discount_name = get_code_discount(code)
	if not discount_name:
		return _("{0} is no longer a valid discount code.").format(code)
	if is_single_use_spent(code):
		return _("{0} has already been used.").format(code)
	discount = get_discount(discount_name)
	if reason := discount.get_unusable_reason():
		return reason
	if discount.once_per_customer and has_used_before(discount.name, get_cart_context(doc)):
		return _("You have already used {0}.").format(discount.title)
	return get_discount_code_refusal(doc, code)


def is_single_use_spent(code: str) -> bool:
	is_generated, times_used = frappe.get_cached_value(
		"Commera Discount Code", code, ["is_generated", "times_used"]
	)
	return bool(is_generated and times_used)


def get_candidates(doc) -> list[Selection]:
	if doc.flags.commera_discounts is not None:
		return [Selection(discount) for discount in doc.flags.commera_discounts]

	candidates = []
	for code in get_discount_codes(doc):
		discount_name = get_code_discount(code)
		if discount_name and not is_single_use_spent(code) and not get_discount_code_refusal(doc, code):
			candidates.append(Selection(get_discount(discount_name), code))
	automatic = frappe.get_all(
		"Commera Discount", filters={"enabled": 1, "method": "Automatic"}, pluck="name", order_by="creation"
	)
	return candidates + [Selection(get_discount(name)) for name in automatic]


def get_unmet_reason(discount: CommeraDiscount, cart) -> str | None:
	if reason := discount.get_unmet_condition(cart):
		return reason
	is_first = cart.doc.flags.commera_first_order
	if discount.eligibility == "First Order" and not (
		is_first if is_first is not None else is_first_order(cart)
	):
		return _("{0} is for a first order only.").format(discount.title)
	if discount.once_per_customer and has_used_before(discount.name, cart):
		return _("You have already used {0}.").format(discount.title)
	return None
