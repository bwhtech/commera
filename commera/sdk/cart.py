import frappe
from frappe import _
from frappe.utils.data import flt

from commera.api.payments import cart_write_lock, save_cart_quotation, validate_cart_is_not_in_checkout
from commera.api.shipping import get_checkout_summary
from commera.checkout_hooks import apply_plugin_fees
from commera.commera_ecommerce.doctype.commera_cart.commera_cart import CommeraCart, get_session_cart
from commera.core import _get_cart_quotation
from commera.plugin_events import get_plugin_fieldnames, validate_plugin_fieldnames
from commera.sdk.types import Cart, CheckoutSummary, NewCartLine, PricedCart

__all__ = [
	"add_discount_code",
	"add_lines",
	"get_cart",
	"get_priced_cart",
	"remove_discount_code",
	"remove_lines",
	"set_cart_fields",
	"update_lines",
]


def get_cart() -> Cart | None:
	"""The session shopper's cart, a guest's included, or None when they have not started one."""
	quotation = _get_cart_quotation()
	if quotation.is_new():
		return None

	return {
		"name": quotation.name,
		"customer": quotation.party_name if quotation.quotation_to == "Customer" else None,
		"currency": quotation.currency,
		"items": [
			{
				"item_code": row.item_code,
				"title": row.item_name,
				"qty": flt(row.qty),
				"rate": flt(row.rate),
				"amount": flt(row.amount),
			}
			for row in quotation.items
		],
		"total": flt(quotation.total),
		"grand_total": flt(quotation.grand_total),
		"plugin_fields": {
			fieldname: quotation.get(fieldname) for fieldname in get_plugin_fieldnames("Quotation")
		},
	}


def set_cart_fields(values: dict) -> CheckoutSummary:
	"""Save an app's own Quotation fields on the shopper's cart and re-price its plugin fees. Each field must
	start with the name of an installed Commera plugin; a cart already in payment is refused."""
	validate_plugin_fieldnames("Quotation", values)
	quotation = _get_cart_quotation()
	if quotation.is_new():
		frappe.throw(_("Add something to your cart first."), frappe.DoesNotExistError)

	with cart_write_lock(quotation):
		validate_cart_is_not_in_checkout(quotation.name)
		quotation.update(values)
		apply_plugin_fees(quotation)
		save_cart_quotation(quotation)
		return get_checkout_summary(quotation)


def get_priced_cart() -> PricedCart | None:
	"""The session shopper's server cart with lines, attributes and code discounts, or None."""
	cart = get_session_cart()
	return cart.get_priced_cart() if cart else None


def add_lines(lines: list[NewCartLine]) -> PricedCart:
	"""Add lines to the session shopper's server cart, starting one when they have none. The storefront
	shows the new lines on the shopper's next page load."""
	cart = get_session_cart(create=True)
	cart.add_lines(lines)
	return save_server_cart(cart)


def update_lines(lines: list[dict]) -> PricedCart:
	"""Set `qty` or `attributes` per `line_id`. A quantity of 0 removes the line."""
	cart = get_existing_cart()
	cart.update_lines(lines)
	return save_server_cart(cart)


def remove_lines(line_ids: list[str]) -> PricedCart:
	cart = get_existing_cart()
	cart.remove_lines(line_ids)
	return save_server_cart(cart)


def add_discount_code(code: str) -> PricedCart:
	"""Apply a Commera Discount code, refused when it is invalid or does not combine with the codes applied."""
	cart = get_existing_cart()
	cart.add_discount_code(code)
	return save_server_cart(cart)


def remove_discount_code(code: str) -> PricedCart:
	cart = get_existing_cart()
	cart.remove_discount_code(code)
	return save_server_cart(cart)


def get_existing_cart() -> CommeraCart:
	cart = get_session_cart()
	if not cart:
		frappe.throw(_("Add something to your cart first."), frappe.DoesNotExistError)
	return cart


def save_server_cart(cart: CommeraCart) -> PricedCart:
	cart.save(ignore_permissions=True)
	return cart.get_priced_cart()
