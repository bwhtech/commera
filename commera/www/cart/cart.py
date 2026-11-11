from frappe import _

from commera.localization.cart_currency import get_cart_delivery_configuration


no_cache = True


def get_context(context):
	context.delivery_charge, context.delivery_charge_applicable_below = get_cart_delivery_configuration()
	context.breadcrumbs = [
		{
			"label": _("Cart"),
			"href": "#",
		}
	]
