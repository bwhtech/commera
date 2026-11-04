import frappe
from frappe import _

from commera.guest import is_guest
from commera.utils import get_same_site_path

no_cache = True


def get_context(context):
	"""OTP sign-in for a headless storefront. `redirect-to` must be a path on this site;
	`prompt=login` asks for a sign-in even when the browser is signed in already."""
	redirect_to = get_same_site_path(frappe.form_dict.get("redirect-to")) or "/"
	if not is_guest() and frappe.form_dict.get("prompt") != "login":
		frappe.local.flags.redirect_location = redirect_to
		raise frappe.Redirect

	context.redirect_to = redirect_to
	context.signed_in_user = None if is_guest() else frappe.session.user
	context.title = _("Sign In")
	context.show_breadcrumb = False
