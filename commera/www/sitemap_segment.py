from urllib.parse import quote

import frappe
from frappe.utils import get_datetime, get_url
from frappe.utils.data import cint

from commera.localization.urls import SiteLocales, alternates, get_locale_roots

DEFAULT_URLS_PER_SITEMAP = 50000
# RFC 3986 reserved characters and "%": an encoded path stays as it is.
URL_SAFE_CHARACTERS = ":/?#[]@!$&'()*+,;=%~"


def get_urls_per_page():
	urls_per_sitemap = cint(frappe.db.get_single_value("Commera Settings", "sitemap_urls_per_page"))
	return urls_per_sitemap if urls_per_sitemap > 0 else DEFAULT_URLS_PER_SITEMAP


def get_docs_per_page(locales: SiteLocales | None = None):
	# Every route is emitted once per published language and market URL.
	roots = locales.roots if locales else get_locale_roots()
	return max(get_urls_per_page() // len(roots), 1)


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


def add_localized(urls, path, lastmod, changefreq, priority, locales):
	"""One entry per locale URL of `path`, from alternates(). A one-language store has one."""
	locations = [alt["href"] for alt in alternates(path, locales)] or [get_url(path)]
	for location in locations:
		urls.append(
			{
				"loc": quote(location, safe=URL_SAFE_CHARACTERS),
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
	total = frappe.db.count(config["doctype"], get_segment_filters(config)) + get_homepage_slots(config)
	return -(-total // get_docs_per_page())  # ceil without float math


def get_homepage_slots(config) -> int:
	"""The homepage takes the first route slot of the segment that lists it."""
	return 1 if config.get("include_homepage") else 0


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

	locales = SiteLocales.load()
	docs_per_page = get_docs_per_page(locales)
	homepage = get_homepage_slots(config)
	start = (page - 1) * docs_per_page
	if start < homepage:
		add_localized(urls, "/", None, config["changefreq"], config["priority"], locales)

	# A page length of 0 means no limit.
	length = docs_per_page - max(homepage - start, 0)
	if length < 1:
		return
	route_field = config["route_field"]
	rows = frappe.get_all(
		config["doctype"],
		filters=get_segment_filters(config),
		fields=[route_field, "modified"],
		order_by="modified desc",
		limit_start=max(start - homepage, 0),
		limit_page_length=length,
	)
	for row in rows:
		route = row.get(route_field)
		add_localized(
			urls,
			config["build_path"](route),
			format_lastmod(row.modified),
			config["changefreq"],
			config["priority"],
			locales,
		)
