import frappe

from commera import seo
from commera.commera_ecommerce.doctype.shop_web_page.shop_web_page import (
	get_page_by_route,
	get_page_content,
)
from commera.localization import get_request_path

# An unpublished page renders for its editors only, so this response is user-specific.
no_cache = True


def get_context(context):
	if not build_page_context(context):
		raise frappe.DoesNotExistError

	return context


def build_page_context(context):
	"""Fill `context` from the page on the requested route. Returns False when there is none.

	Shared with the themed renderers, which draw their own not-found state instead of 404ing.
	"""
	page = get_page_by_route(frappe.form_dict.get("route"))
	if not page:
		# ponytail: a themed miss renders the theme's not-found block with 200 + noindex, so keep
		# crawlers off it; thread a status code through ThemePageRenderer to make it a real 404.
		context.seo = seo.build_page_seo({"noindex": 1}, display_name=frappe._("Page not found"))
		context.show_breadcrumb = False
		return False

	context.page = page
	context.content = get_page_content(page)
	context.breadcrumbs = [{"label": page.name, "href": get_request_path()}]
	context.seo = seo.build_page_seo(page, display_name=page.name)
	context.json_ld = [seo.build_breadcrumb_json_ld(context.breadcrumbs)]
	return True
