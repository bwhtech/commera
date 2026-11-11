import frappe
from frappe import _

from commera.localization import url
from commera.localization.address_countries import AddressCountries
from commera.utils import get_addresses, get_country_list

no_cache = True


def get_context(context):
	if frappe.session.user == "Guest":
		raise frappe.PermissionError
	context.billing_addresses = get_addresses()
	context.shipping_addresses = get_addresses(address_type="Shipping")
	context.country_list = AddressCountries.current().within(get_country_list())
	context.breadcrumbs = [
		{
			"label": _("My Account"),
			"href": url("/account/"),
		},
		{
			"label": _("Address"),
			"href": "#",
		},
	]
