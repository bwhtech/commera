import frappe
from frappe import _
from frappe.utils.data import cstr

from commera.guest import is_guest

no_cache = True


def get_context(context):
	"""Hands a storefront checkout code to a POST: a guest browser's form submits itself, a signed-in
	browser confirms before the guest cart merges into its account cart."""
	context.code = cstr(frappe.form_dict.get("code"))
	context.forwarded_params = {
		key: cstr(value)
		for key, value in frappe.form_dict.items()
		if key not in ("code", "cmd", "csrf_token")
	}
	context.signed_in_user = None if is_guest() else frappe.session.user
	context.cart_url = f"/{frappe.local.lang}/cart"
	context.title = _("Continue to Checkout") if is_guest() else _("Add to Your Cart")
	context.show_breadcrumb = False
