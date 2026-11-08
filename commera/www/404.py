import frappe
from markupsafe import Markup

from commera.shop_themes.theme_resolver import get_theme_not_found_html

no_cache = 1


def get_context(context):
	"""Serve the active theme's 404 page for any unknown route, so a shopper stays in the storefront."""
	context.http_status_code = 404
	request = getattr(frappe.local, "request", None)
	html = get_theme_not_found_html(request.path if request else "404")
	context.theme_not_found_html = Markup(html) if html else None
