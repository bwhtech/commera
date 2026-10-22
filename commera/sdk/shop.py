import frappe
from frappe import _
from frappe.utils.data import cint, cstr

from commera.branding import get_brand_assets
from commera.commera_ecommerce.doctype.shop_web_page.shop_web_page import get_page_by_route
from commera.sdk.catalog import get_collection_handle, get_store_currency, list_collections
from commera.sdk.types import ContentPage, FooterSection, MenuItem, Shop, Sitemap, SitemapEntry
from commera.shop_data import get_storefront_menu

__all__ = ["get_page", "get_shop", "get_sitemap"]

SITEMAP_PAGE_SIZE = 5000
SITEMAP_KINDS = ("products", "collections", "pages")
# The doctype and filters of each kind that is read from the database.
SITEMAP_DOCTYPES = {
	"products": ("Style Attribute Variant", {"is_published": 1, "noindex": 0}),
	"pages": ("Shop Web Page", {"published": 1, "noindex": 0}),
}


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
	page = max(cint(page), 1)
	sitemap = {"total": {}, "page": page, "page_size": SITEMAP_PAGE_SIZE}
	for each_kind in [kind] if kind else SITEMAP_KINDS:
		sitemap[each_kind], sitemap["total"][each_kind] = get_sitemap_entries(each_kind, page)
	return sitemap


def get_sitemap_entries(kind: str, page: int) -> tuple[list[SitemapEntry], int]:
	start = (page - 1) * SITEMAP_PAGE_SIZE
	if kind == "collections":
		collections = list_collections()
		return [
			{"handle": collection["handle"], "updated_at": collection["updated_at"]}
			for collection in collections[start : start + SITEMAP_PAGE_SIZE]
		], len(collections)

	doctype, filters = SITEMAP_DOCTYPES[kind]
	rows = frappe.get_all(
		doctype,
		filters=filters,
		fields=["route as handle", "modified as updated_at"],
		# A stable order, so a change to a record does not move it to another page.
		order_by="name asc",
		offset=start,
		limit=SITEMAP_PAGE_SIZE,
	)
	entries = [{"handle": row.handle, "updated_at": str(row.updated_at)} for row in rows]
	return entries, frappe.db.count(doctype, filters)


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
