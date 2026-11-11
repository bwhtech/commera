from frappe import _

# import frappe
from commera.utils import get_delivery_configuration

no_cache = True


def get_context(context):
	context.delivery_charge, context.delivery_charge_applicable_below = get_delivery_configuration()
	context.breadcrumbs = [
		{
			"label": _("Cart"),
			"href": "#",
		}
	]
