import frappe

no_cache = True
from frappe.query_builder import DocType
from frappe.query_builder.functions import Min

from commera import seo
from commera.commera_ecommerce.doctype.landing_page_settings.landing_page_settings import (
	get_translated_landing_page,
)
from commera.utils import get_product_list


def get_context(context):
	homepage_details = get_homepage_details()
	context.homepage_details = homepage_details
	new_arrivals = [item.item_variant for item in homepage_details.get("new_arrivals", [])]
	best_picks = [item.item_variant for item in homepage_details.get("best_picks", [])]

	best_picks = get_product_list(product_list=best_picks, page_length=len(best_picks) or 6)
	new_arrivals = get_product_list(product_list=new_arrivals, page_length=len(new_arrivals) or 6)

	context["new_arrivals"] = new_arrivals
	context["best_picks"] = best_picks

	set_home_seo(context)


def set_home_seo(context):
	context.show_breadcrumb = False
	settings = seo.get_seo_settings()
	context.seo = seo.build_page_seo(
		{
			"meta_title": settings.get("homepage_meta_title"),
			"meta_description": settings.get("homepage_meta_description"),
			"og_image": settings.get("homepage_og_image"),
		}
	)
	context.json_ld = seo.org_website_json_ld()


def get_homepage_details():
	"""The homepage settings, with the banners, GIFs and their links in the request language."""
	settings = frappe.get_cached_doc("Landing Page Settings")
	details = get_translated_landing_page(settings)
	details.new_arrivals = settings.new_arrivals
	details.best_picks = settings.best_picks
	return details
