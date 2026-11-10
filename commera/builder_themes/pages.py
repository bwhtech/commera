import frappe

HOME = "Home"
PRODUCT_LISTING = "Product Listing"
PRODUCT_DETAIL = "Product Detail"

PAGE_TABLE = "Shop Theme Builder Page"

# The themed routes a Builder theme takes over; every other route renders from its parent theme.
PAGE_TYPE_BY_TEMPLATE = {
	"pages/index.html": HOME,
	"pages/products/list.html": PRODUCT_LISTING,
	"pages/products/details.html": PRODUCT_DETAIL,
}

STOREFRONT_PATHS = {
	HOME: "/en",
	PRODUCT_LISTING: "/en/products",
	PRODUCT_DETAIL: "/en/products/<product handle>",
}


def get_theme_pages(theme_name: str) -> dict[str, str]:
	"""Builder page name by page type."""
	rows = frappe.get_all(
		PAGE_TABLE,
		filters={"parent": theme_name, "parenttype": "Shop Theme"},
		fields=["page_type", "builder_page"],
		order_by="idx asc",
	)
	return {row.page_type: row.builder_page for row in rows}


def get_page_role(page_name: str) -> frappe._dict | None:
	"""The theme and page type a Builder page plays, or None for a page outside every Commera theme."""
	return frappe.db.get_value(
		PAGE_TABLE,
		{"builder_page": page_name, "parenttype": "Shop Theme"},
		["parent as theme", "page_type"],
		as_dict=True,
	)


def is_builder_installed() -> bool:
	return "builder" in frappe.get_installed_apps()


def get_editor_url(page_name: str) -> str:
	from builder.utils import get_builder_path

	return f"/{get_builder_path()}/page/{page_name}"
