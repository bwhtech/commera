import frappe

from commera.sdk.format import url


def get_context(context):
	"""The starter's account home is the orders list; the legacy dashboard route lands there."""
	frappe.flags.redirect_location = url("/account/orders")
	raise frappe.Redirect(302)
