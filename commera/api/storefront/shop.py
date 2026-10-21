from urllib.parse import quote

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cstr

from commera.api.storefront.collections import get_collection_handle, get_collections
from commera.api.storefront.products import get_currency
from commera.branding import get_brand_assets
from commera.commera_ecommerce.doctype.shop_web_page.shop_web_page import get_page_by_route
from commera.shop_data import get_storefront_menu

SITEMAP_LIMIT = 5000


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60)
def get_shop() -> dict:
	"""Store identity, navigation and footer for a headless storefront."""
	settings = frappe.get_cached_doc("Commera Settings")
	brand = get_brand_assets()
	return {
		"name": settings.store_name or frappe.get_website_settings("app_name") or "Commera",
		"description": settings.default_meta_description or "",
		"currency": get_currency(),
		"logo": brand.logo,
		"favicon": brand.favicon,
		"menu": [get_menu_item(node) for node in get_storefront_menu() if node.get("visible", 1)],
		"footer": get_footer(settings),
	}


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60)
def get_page(handle: str) -> dict:
	page = get_page_by_route(cstr(handle))
	if not page or not page.published:
		raise frappe.DoesNotExistError(_("Page {0} not found").format(handle))
	return {
		"handle": page.route,
		"title": page.meta_title or page.name,
		"body_html": page.content or "",
		"seo": {
			"title": page.meta_title,
			"description": page.meta_description,
			"noindex": bool(page.noindex),
		},
		"updated_at": str(page.modified),
	}


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=60, seconds=60)
def get_sitemap() -> dict:
	"""Every indexable product, collection and page handle with its last change."""
	products = frappe.get_all(
		"Style Attribute Variant",
		filters={"is_published": 1, "noindex": 0},
		fields=["route as handle", "modified as updated_at"],
		order_by="modified desc",
		limit=SITEMAP_LIMIT,
	)
	pages = frappe.get_all(
		"Shop Web Page",
		filters={"published": 1, "noindex": 0},
		fields=["route as handle", "modified as updated_at"],
		limit=SITEMAP_LIMIT,
	)
	collections = [
		{"handle": collection["handle"], "updated_at": collection["updated_at"]}
		for collection in get_collections()
	]
	return {
		"products": [{**row, "updated_at": str(row.updated_at)} for row in products],
		"collections": collections,
		"pages": [{**row, "updated_at": str(row.updated_at)} for row in pages],
	}


def get_menu_item(node: dict) -> dict:
	return {
		"title": node["label"],
		"url": get_menu_url(node),
		"items": [get_menu_item(child) for child in node.get("children") or [] if child.get("visible", 1)],
	}


def get_menu_url(node: dict) -> str | None:
	"""Storefront paths: an Item Group link opens its collection, a Brand link searches for the brand."""
	if node["link_type"] == "URL":
		return node["url"] or None
	if node["link_type"] == "Brand" and node["brand"]:
		return f"/search?q={quote(node['brand'])}"
	if node["link_type"] == "Item Group" and node["item_groups"]:
		return f"/collections/{get_collection_handle(node['item_groups'][0])}"
	# A root tab without item groups filters nothing on the Commera storefront either.
	return None if node["parent"] else "/collections/all"


def get_footer(settings) -> list[dict]:
	sections = sorted(
		(row for row in settings.footer_sections or [] if row.enabled), key=lambda row: row.section_order
	)
	return [get_footer_section(row.footer_section) for row in sections]


def get_footer_section(name: str) -> dict:
	section = frappe.get_cached_doc("Footer Section Config", name)
	links = sorted((link for link in section.footer_links if link.enabled), key=lambda link: link.link_order)
	return {
		"title": section.section_title,
		"links": [{"title": link.link_label, "url": link.link_url} for link in links],
	}
