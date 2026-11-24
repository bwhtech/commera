import frappe
from frappe import _
from frappe.www.login import sanitize_redirect

from commera.sdk.format import url
from commera.seo import apply_title_template, default_seo

no_cache = True


def get_context(context):
	context.redirect_to = sanitize_redirect(frappe.form_dict.get("redirect-to")) or url("/account/orders")
	if frappe.session.user != "Guest":
		frappe.flags.redirect_location = context.redirect_to
		raise frappe.Redirect(302)
	context.seo = {**default_seo(), "title": apply_title_template(_("Create an account")), "noindex": True}
	return context
