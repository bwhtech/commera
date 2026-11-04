import frappe

no_cache = True
from frappe.query_builder import DocType
from frappe.query_builder.functions import Min

from commera import seo
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
	homepage_settings = frappe.get_cached_doc("Landing Page Settings")
	homepage_details = {}
	if frappe.local.lang == "ar":
		homepage_details = {
			"hero_banner": homepage_settings.hero_banner_ar or homepage_settings.hero_banner,
			"new_arrivals": homepage_settings.new_arrivals,
			"best_picks": homepage_settings.best_picks,
			"gif_1": homepage_settings.gif_1_ar or homepage_settings.gif_1,
			"gif_url_1": homepage_settings.gif_url_1_ar or homepage_settings.gif_url_1,
			"gif_2": homepage_settings.gif_2_ar or homepage_settings.gif_2,
			"gif_url_2": homepage_settings.gif_url_2_ar or homepage_settings.gif_url_2,
			"gif_3": homepage_settings.gif_3_ar or homepage_settings.gif_3,
			"gif_url_3": homepage_settings.gif_url_3_ar or homepage_settings.gif_url_3,
			"gif_4": homepage_settings.gif_4_ar or homepage_settings.gif_4,
			"gif_url_4": homepage_settings.gif_url_4_ar or homepage_settings.gif_url_4,
			"banner_1": homepage_settings.banner_1_ar or homepage_settings.banner_1,
			"banner_url_1": homepage_settings.banner_url_1_ar or homepage_settings.banner_url_1,
		}
	else:
		homepage_details = {
			"hero_banner": homepage_settings.hero_banner,
			"new_arrivals": homepage_settings.new_arrivals,
			"best_picks": homepage_settings.best_picks,
			"gif_1": homepage_settings.gif_1,
			"gif_url_1": homepage_settings.gif_url_1,
			"gif_2": homepage_settings.gif_2,
			"gif_url_2": homepage_settings.gif_url_2,
			"gif_3": homepage_settings.gif_3,
			"gif_url_3": homepage_settings.gif_url_3,
			"gif_4": homepage_settings.gif_4,
			"gif_url_4": homepage_settings.gif_url_4,
			"banner_1": homepage_settings.banner_1,
			"banner_url_1": homepage_settings.banner_url_1,
		}
	return homepage_details
