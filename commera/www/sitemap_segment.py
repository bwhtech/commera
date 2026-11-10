import frappe
from frappe.utils import get_datetime, get_url
from frappe.utils.data import cint

from commera.localization.urls import get_locale_prefixes

DEFAULT_URLS_PER_SITEMAP = 50000


def get_urls_per_page():
	urls_per_sitemap = cint(frappe.db.get_single_value("Commera Settings", "sitemap_urls_per_page"))
	return urls_per_sitemap if urls_per_sitemap > 0 else DEFAULT_URLS_PER_SITEMAP


def get_docs_per_page():
	# Every route is emitted once per published language and market URL.
	return max(get_urls_per_page() // len(get_language_prefixes()), 1)


def get_language_prefixes():
	"""URL prefixes of the published languages and enabled market URLs. The default language has none."""
	return [prefix for _hreflang, prefix, _x_default in get_locale_prefixes()]


SEGMENT_CONFIG = {
	"products": {
		"doctype": "Style Attribute Variant",
		"filters": {"is_published": 1, "noindex": 0},
		"route_field": "route",
		"build_path": lambda route: f"/products/{route}",
		"changefreq": "weekly",
		"priority": "0.8",
	},
	"collections": {
		"doctype": "Ecommerce Category",
		"filters": {"enabled": 1, "noindex": 0},
		"route_field": "route_slug",
		"build_path": lambda route_slug: f"/products?category={route_slug}",
		"changefreq": "daily",
		"priority": "0.6",
	},
	"pages": {
		"doctype": "Shop Web Page",
		"filters": {"published": 1, "noindex": 0},
		"route_field": "route",
		"build_path": lambda route: f"/page/{route}",
		"include_homepage": True,
		"changefreq": "daily",
		"priority": "1.0",
	},
}


def format_lastmod(value):
	if not value:
		return None
	return get_datetime(value).isoformat()


def add_localized(urls, path, lastmod, changefreq, priority):
	for prefix in get_language_prefixes():
		urls.append(
			{
				"loc": get_url(f"{prefix}{path}" or "/"),
				"lastmod": lastmod,
				"changefreq": changefreq,
				"priority": priority,
			}
		)


def get_segment_filters(config):
	"""Rows with no route emit no URL: most Ecommerce Category rows are nested and carry no route_slug."""
	return {**config["filters"], config["route_field"]: ["is", "set"]}


def segment_page_count(seg_type):
	config = SEGMENT_CONFIG[seg_type]
	total = frappe.db.count(config["doctype"], get_segment_filters(config))
	page_count = -(-total // get_docs_per_page())  # ceil without float math
	return max(page_count, 1) if config.get("include_homepage") else page_count


def latest_lastmod(seg_type):
	config = SEGMENT_CONFIG[seg_type]
	rows = frappe.get_all(
		config["doctype"],
		filters=get_segment_filters(config),
		fields=["modified"],
		order_by="modified desc",
		limit=1,
	)
	if not rows:
		return None
	return format_lastmod(rows[0].modified)


def get_context(context):
	# Stay out of the page cache so freshly published routes appear promptly.
	context.no_cache = 1

	seg_type = frappe.form_dict.get("seg_type")
	page = cint(frappe.form_dict.get("page"))

	urls = []
	context.urls = urls

	config = SEGMENT_CONFIG.get(seg_type)
	if not config or page < 1:
		return

	if page == 1 and config.get("include_homepage"):
		add_localized(urls, "", None, config["changefreq"], config["priority"])

	docs_per_page = get_docs_per_page()
	route_field = config["route_field"]
	rows = frappe.get_all(
		config["doctype"],
		filters=get_segment_filters(config),
		fields=[route_field, "modified"],
		order_by="modified desc",
		limit_start=(page - 1) * docs_per_page,
		limit_page_length=docs_per_page,
	)
	for row in rows:
		route = row.get(route_field)
		add_localized(
			urls,
			config["build_path"](route),
			format_lastmod(row.modified),
			config["changefreq"],
			config["priority"],
		)
