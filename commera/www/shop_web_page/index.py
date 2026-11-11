import frappe

from commera import seo
from commera.commera_ecommerce.doctype.shop_web_page.shop_web_page import (
	get_page_by_route,
	get_translated_page,
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

	values = {field: value.value for field, value in get_translated_page(page).items()}
	context.page = page
	context.page_title = values["title"]
	context.content = values["content"]
	context.breadcrumbs = [{"label": values["title"], "href": get_request_path()}]
	seo_source = {
		"meta_title": values["meta_title"],
		"meta_description": values["meta_description"],
		"og_image": page.og_image,
		"noindex": page.noindex,
	}
	context.seo = seo.build_page_seo(seo_source, display_name=values["title"])
	context.json_ld = [seo.build_breadcrumb_json_ld(context.breadcrumbs)]
	return True
