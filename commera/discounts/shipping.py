from frappe.utils.data import flt

from commera.discounts.cart_context import get_cart_context
from commera.discounts.doctype.commera_discount.commera_discount import SHIPPING
from commera.discounts.pricing import select_discounts


def apply_shipping_discounts(quotation, options: list[dict]) -> list[dict]:
	# Runs after the plugin hooks, so shown price equals charged price.
	return [get_discounted_option(option, quotation) for option in options]


def get_discounted_option(option: dict, quotation) -> dict:
	cart = get_cart_context(quotation)
	cart.offered_option = option
	selections = [s for s in select_discounts(cart) if s.discount.discount_class == SHIPPING]
	if not selections:
		return option
	best_amount, best_discount = max(
		(s.discount.get_delivery_discount(option, cart), s.discount.name) for s in selections
	)
	if not best_amount:
		return option
	option = dict(option)
	option["original_amount"] = option["amount"]
	option["amount"] = flt(option["amount"] - best_amount, 2)
	option["is_free"] = not option["amount"]
	option["shipping_discount"] = best_discount
	return option


def set_shipping_discount(quotation, option: dict | None):
	option = option or {}
	original_amount = flt(option.get("original_amount"))
	quotation.custom_shipping_discount = original_amount - flt(option.get("amount")) if original_amount else 0
	quotation.custom_shipping_discount_id = option.get("shipping_discount")
