import frappe
from frappe import _
from frappe.utils.data import cint, cstr

from commera.branding import get_brand_assets
from commera.commera_ecommerce.doctype.shop_web_page.shop_web_page import get_page_by_route
from commera.sdk.types import ContentPage, FooterSection, MenuItem, Shop, Sitemap, SitemapEntry
from commera.shop_data import get_storefront_menu
from commera.utils import get_store_currency
from commera.www.sitemap_segment import SEGMENT_CONFIG, get_segment_filters, get_urls_per_page

__all__ = ["get_page", "get_shop", "get_sitemap"]

SITEMAP_KINDS = tuple(SEGMENT_CONFIG)


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


def get_sitemap(kind: str | None = None, page: int = 1) -> Sitemap:
	"""One page of indexable handles with their last change, for `kind` or else for every kind. `total`
	counts the handles of each returned kind."""
	if kind is not None and kind not in SITEMAP_KINDS:
		frappe.throw(_("Sitemap kind must be one of {0}.").format(", ".join(SITEMAP_KINDS)))
	page, page_size = max(cint(page), 1), get_urls_per_page()
	sitemap = {"total": {}, "page": page, "page_size": page_size}
	for each_kind in [kind] if kind else SITEMAP_KINDS:
		sitemap[each_kind], sitemap["total"][each_kind] = get_sitemap_entries(each_kind, page, page_size)
	return sitemap


def get_sitemap_entries(kind: str, page: int, page_size: int) -> tuple[list[SitemapEntry], int]:
	config = SEGMENT_CONFIG[kind]
	filters = get_segment_filters(config)
	rows = frappe.get_all(
		config["doctype"],
		filters=filters,
		fields=[f"{config['route_field']} as handle", "modified as updated_at"],
		# A stable order, so a change to a record does not move it to another page.
		order_by="name asc",
		offset=(page - 1) * page_size,
		limit=page_size,
	)
	entries = [{"handle": row.handle, "updated_at": str(row.updated_at)} for row in rows]
	return entries, frappe.db.count(config["doctype"], filters)


def get_menu_item(node: dict, root_slug: str | None = None) -> MenuItem:
	root_slug = root_slug or node["route_slug"]
	link_type, target = get_menu_link(node, root_slug)
	return {
		"title": node["label"],
		"type": link_type,
		"target": target,
		"items": [
			get_menu_item(child, root_slug) for child in node.get("children") or [] if child.get("visible", 1)
		],
	}


def get_menu_link(node: dict, root_slug: str) -> tuple[str | None, str | None]:
	"""A nested Item Group entry links its tab's collection: collections are the tabs only."""
	if node["link_type"] == "URL":
		return ("url", node["url"]) if node["url"] else (None, None)
	if node["link_type"] == "Brand" and node["brand"]:
		return "brand", node["brand"]
	if (node["link_type"] == "Item Group" and node["item_groups"]) or not node["parent"]:
		return ("collection", root_slug) if root_slug else ("all", None)
	return None, None


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
