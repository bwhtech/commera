import frappe
from frappe import _

from commera.utils import get_addresses

no_cache = True


def get_context(context):
	if frappe.session.user == "Guest":
		raise frappe.PermissionError
	context.user_details = frappe.get_cached_doc("User", frappe.session.user)

	billing_addresses = get_addresses()
	billing_addresses = billing_addresses[0] if billing_addresses else []

	context.billing_address = billing_addresses
	context.breadcrumbs = [
		{
			"label": _("My Account"),
			"href": "#",
		}
	]
