import frappe
from frappe.utils.data import cstr

from commera.branding import get_brand_assets
from commera.commera_ecommerce.doctype.shop_web_page.shop_web_page import get_page_by_route
from commera.sdk.catalog import get_collection_handle, get_store_currency, list_collections
from commera.sdk.types import ContentPage, FooterSection, MenuItem, Shop, SitemapEntry
from commera.shop_data import get_storefront_menu

__all__ = ["get_page", "get_shop", "get_sitemap"]

SITEMAP_LIMIT = 5000


def get_shop() -> Shop:
	"""Store identity, the storefront menu and the footer."""
	settings = frappe.get_cached_doc("Commera Settings")
	brand = get_brand_assets()
	return {
		"name": settings.store_name or frappe.get_website_settings("app_name") or "Commera",
		"description": settings.default_meta_description or "",
		"currency": get_store_currency(),
		"logo": brand.logo,
		"favicon": brand.favicon,
		"menu": [get_menu_item(node) for node in get_storefront_menu() if node.get("visible", 1)],
		"footer": [get_footer_section(row.footer_section) for row in get_footer_rows(settings)],
	}


def get_page(handle: str) -> ContentPage | None:
	"""A published Shop Web Page by its route, or None."""
	page = get_page_by_route(cstr(handle))
	if not page or not page.published:
		return None
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


def get_sitemap() -> dict[str, list[SitemapEntry]]:
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
	return {
		"products": [{"handle": row.handle, "updated_at": str(row.updated_at)} for row in products],
		"collections": [
			{"handle": collection["handle"], "updated_at": collection["updated_at"]}
			for collection in list_collections()
		],
		"pages": [{"handle": row.handle, "updated_at": str(row.updated_at)} for row in pages],
	}


def get_menu_item(node: dict) -> MenuItem:
	link_type, target = get_menu_link(node)
	return {
		"title": node["label"],
		"type": link_type,
		"target": target,
		"items": [get_menu_item(child) for child in node.get("children") or [] if child.get("visible", 1)],
	}


def get_menu_link(node: dict) -> tuple[str | None, str | None]:
	if node["link_type"] == "URL":
		return ("url", node["url"]) if node["url"] else (None, None)
	if node["link_type"] == "Brand" and node["brand"]:
		return "brand", node["brand"]
	if node["link_type"] == "Item Group" and node["item_groups"]:
		return "collection", get_collection_handle(node["item_groups"][0])
	# A root tab without item groups filters nothing on the Commera storefront either.
	return (None, None) if node["parent"] else ("all", None)


def get_footer_rows(settings) -> list:
	return sorted(
		(row for row in settings.footer_sections or [] if row.enabled), key=lambda row: row.section_order
	)


def get_footer_section(name: str) -> FooterSection:
	section = frappe.get_cached_doc("Footer Section Config", name)
	links = sorted((link for link in section.footer_links if link.enabled), key=lambda link: link.link_order)
	return {
		"title": section.section_title,
		"links": [{"title": link.link_label, "url": link.link_url} for link in links],
	}
