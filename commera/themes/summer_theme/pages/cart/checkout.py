from commera.guest import is_guest_checkout_enabled
from commera.www.cart import checkout


def get_context(context):
	checkout.get_context(context, allow_guest=is_guest_checkout_enabled())
	return context
