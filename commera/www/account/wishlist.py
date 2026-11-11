import frappe
from frappe import _

from commera.localization import url

no_cache = True


def get_context(context):
	context.breadcrumbs = [
		{
			"label": _("My Account"),
			"href": url("/account/"),
		},
		{
			"label": _("Wishlist"),
			"href": "#",
		},
	]
