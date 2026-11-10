"""What the Commera theme bar in the Builder editor shows and does."""

import frappe
from frappe import _

from commera.builder_themes.pages import HOME, PRODUCT_DETAIL, PRODUCT_LISTING, get_page_role, get_theme_pages
from commera.sdk import catalog
from commera.sdk.format import image_url
from commera.shop_themes.doctype.shop_theme.shop_theme import resolve_active_theme

PREVIEW_PRODUCT_COUNT = 12
PREVIEW_IMAGE_WIDTH = 160


def get_theme_bar(page_id: str) -> dict | None:
	"""None for a page outside every Commera theme, so the bar stays out of other pages."""
	role = get_page_role(page_id)
	if not role:
		return None
	return {
		"theme": role.theme,
		"is_live": role.theme == resolve_active_theme(),
		"page_type": role.page_type,
		"pages": [get_page_tab(page_type, page) for page_type, page in get_theme_pages(role.theme).items()],
		"preview": get_preview(role.page_type),
		"storefront_path": get_storefront_path(role.page_type),
	}


def get_page_labels() -> dict[str, str]:
	return {HOME: _("Home"), PRODUCT_LISTING: _("Listing"), PRODUCT_DETAIL: _("Product")}


def get_page_tab(page_type: str, page_name: str) -> dict:
	page = frappe.db.get_value("Builder Page", page_name, ["published", "draft_blocks"], as_dict=True)
	return {
		"page_type": page_type,
		"label": get_page_labels()[page_type],
		"page": page_name,
		"is_published": bool(page.published),
		"has_unpublished_changes": bool(page.draft_blocks) and bool(page.published),
	}


def get_preview(page_type: str) -> dict | None:
	"""What the canvas can preview the page with: a product, or a collection of the listing."""
	if page_type == PRODUCT_DETAIL:
		return {"variable": "route", "label": _("Product"), "options": search_products()}
	if page_type == PRODUCT_LISTING:
		options = [{"value": "", "label": _("All products"), "image": None}]
		options += [
			{"value": collection["handle"], "label": collection["title"], "image": None}
			for collection in catalog.list_collections()
		]
		return {"variable": "category", "label": _("Collection"), "options": options}
	return None


def search_products(query: str | None = None) -> list[dict]:
	if query:
		products = catalog.search(query, page_size=PREVIEW_PRODUCT_COUNT)["products"]
	else:
		products = catalog.list_products(sort="new_arrival", page_size=PREVIEW_PRODUCT_COUNT)["products"]
	return [
		{
			"value": product["handle"],
			"label": product["title"],
			"image": image_url(product["image"], PREVIEW_IMAGE_WIDTH),
		}
		for product in products
	]


def get_storefront_path(page_type: str) -> str:
	language = frappe.local.lang or "en"
	return {HOME: f"/{language}", PRODUCT_LISTING: f"/{language}/products"}.get(
		page_type, f"/{language}/products/"
	)


def publish_theme(theme: str) -> dict:
	"""Publish every page that has been designed. An empty page stays unpublished, so its route keeps
	rendering from the parent theme instead of going blank."""
	labels = get_page_labels()
	published, skipped = [], []
	for page_type, page_name in get_theme_pages(theme).items():
		page = frappe.get_doc("Builder Page", page_name)
		page.check_permission("write")
		if page.block_count() <= 1:
			skipped.append(labels[page_type])
			continue
		page.publish()
		published.append(labels[page_type])
	return {"published": published, "skipped": skipped}
