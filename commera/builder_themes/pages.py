import frappe

HOME = "Home"
PRODUCT_LISTING = "Product Listing"
PRODUCT_DETAIL = "Product Detail"

PAGE_TABLE = "Shop Theme Builder Page"
# Builder also serves each theme page at its own route under this prefix.
ROUTE_PREFIX = "ct"

# The themed routes a Builder theme takes over; every other route renders from its parent theme.
PAGE_TYPE_BY_TEMPLATE = {
	"pages/index.html": HOME,
	"pages/products/list.html": PRODUCT_LISTING,
	"pages/products/details.html": PRODUCT_DETAIL,
}

STOREFRONT_PATHS = {
	HOME: "/",
	PRODUCT_LISTING: "/products",
	PRODUCT_DETAIL: "/products/<product handle>",
}


def get_theme_pages(theme_name: str) -> dict[str, str]:
	"""Builder page name by page type, leaving out a page deleted in Builder: its route falls back to the parent."""
	rows = frappe.get_all(
		PAGE_TABLE,
		filters={"parent": theme_name, "parenttype": "Shop Theme"},
		fields=["page_type", "builder_page"],
		order_by="idx asc",
	)
	if not is_builder_installed():
		return {}
	existing = set(
		frappe.get_all(
			"Builder Page", filters={"name": ["in", [row.builder_page for row in rows]]}, pluck="name"
		)
	)
	return {row.page_type: row.builder_page for row in rows if row.builder_page in existing}


def get_page_role(page_name: str) -> frappe._dict | None:
	"""The theme and page type a Builder page plays, or None for a page outside every Commera theme."""
	return frappe.db.get_value(
		PAGE_TABLE,
		{"builder_page": page_name, "parenttype": "Shop Theme"},
		["parent as theme", "page_type"],
		as_dict=True,
	)


def is_builder_theme_path(path: str) -> bool:
	return path.strip("/").split("/", 1)[0] == ROUTE_PREFIX


def is_builder_installed() -> bool:
	return "builder" in frappe.get_installed_apps()


def get_editor_url(page_name: str) -> str:
	from builder.utils import get_builder_path

	return f"/{get_builder_path()}/page/{page_name}"
