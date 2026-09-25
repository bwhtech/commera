import frappe

from commera.api.payments import cart_write_lock, get_checkout_summary, save_cart_quotation, set_charges
from commera.core import _get_cart_quotation
from commera.utils import get_delivery_configuration


@frappe.whitelist()
def apply_shipping_rule():
	save_checkout_charges()
	return get_delivery_configuration()


@frappe.whitelist()
def save_checkout_charges() -> dict:
	cart_quotation = _get_cart_quotation()
	with cart_write_lock(cart_quotation):
		set_charges(cart_quotation)
		save_cart_quotation(cart_quotation)
	return get_checkout_summary(cart_quotation)
