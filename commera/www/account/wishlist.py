import frappe

from commera.localization import url

no_cache = True


def get_context(context):
	context.breadcrumbs = [
		{
			"label": "My Account",
			"href": url("/account/"),
		},
		{
			"label": "Wishlist",
			"href": "#",
		},
	]
