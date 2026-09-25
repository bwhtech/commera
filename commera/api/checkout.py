import frappe

from commera.api.payments import (
	cart_write_lock,
	get_open_gateway_payment_request,
	save_cart_quotation,
	set_charges,
)
from commera.api.shipping import clear_delivery_option
from commera.core import _get_cart_quotation
from commera.utils import get_delivery_configuration


@frappe.whitelist(methods=["POST"])
def apply_shipping_rule():
	cart_quotation = _get_cart_quotation()
	with cart_write_lock(cart_quotation):
		# Loading checkout in a second tab must not rewrite the cart a shopper is paying for in the first.
		if not get_open_gateway_payment_request(cart_quotation.name):
			# Checkout opens with no delivery option chosen, so the cart must not keep billing the last one.
			clear_delivery_option(cart_quotation)
			set_charges(cart_quotation)
			save_cart_quotation(cart_quotation)
	return get_delivery_configuration()
