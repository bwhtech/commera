import frappe


def get_context(context):
	"""The starter's account home is the orders list; the legacy dashboard route lands there."""
	frappe.flags.redirect_location = f"/{frappe.local.lang or 'en'}/account/orders"
	raise frappe.Redirect(302)
