import frappe
from frappe import _

from commera.builder_themes.pages import (
	HOME,
	PRODUCT_DETAIL,
	PRODUCT_LISTING,
	ROUTE_PREFIX,
	is_builder_installed,
)
from commera.shop_themes.doctype.shop_theme.shop_theme import (
	BUILDER_THEME_TYPE,
	get_starter_theme,
	validate_theme_name,
)

# Builder serves each page at its own route as well; Commera serves the live theme at the storefront routes.
PAGE_ROUTES = {
	HOME: "home",
	PRODUCT_LISTING: "products",
	PRODUCT_DETAIL: "products/:route",
}
HEAD_HTML = "{{ commera_builder_head() }}"
# What Builder's editor gives a new page: an empty body.
ROOT_BLOCK = {
	"element": "div",
	"originalElement": "body",
	"attributes": {},
	"baseStyles": {
		"display": "flex",
		"flexWrap": "wrap",
		"flexShrink": 0,
		"flexDirection": "column",
		"alignItems": "center",
	},
	"blockId": "root",
	"children": [],
}


def create_builder_theme(theme_name: str) -> "frappe.Document":
	"""A Shop Theme whose home, listing and product pages are empty Builder pages in their own folder."""
	if not is_builder_installed():
		frappe.throw(_("Install Frappe Builder on this site to design themes in it"))
	validate_theme_name(theme_name)
	if frappe.db.exists("Shop Theme", theme_name):
		frappe.throw(_("A theme named {0} already exists").format(theme_name))

	folder = create_folder(theme_name)
	theme = frappe.get_doc(
		{
			"doctype": "Shop Theme",
			"theme_name": theme_name,
			"theme_type": BUILDER_THEME_TYPE,
			"parent_theme": get_parent_theme(),
			"builder_folder": folder,
			"builder_pages": [
				{"page_type": page_type, "builder_page": create_page(theme_name, folder, page_type)}
				for page_type in PAGE_ROUTES
			],
		}
	)
	return theme.insert()


def get_parent_theme() -> str:
	"""Cart, checkout and account render from the Sections starter theme."""
	starter = get_starter_theme("Sections")
	if not starter:
		frappe.throw(_("A Builder theme inherits from the starter theme, and this site has none"))
	return starter.name


def create_folder(theme_name: str) -> str:
	if frappe.db.exists("Builder Project Folder", theme_name):
		frappe.throw(_("Frappe Builder already has a folder named {0}").format(theme_name))
	return frappe.get_doc({"doctype": "Builder Project Folder", "folder_name": theme_name}).insert().name


def create_page(theme_name: str, folder: str, page_type: str) -> str:
	page = frappe.get_doc(
		{
			"doctype": "Builder Page",
			# page first: Builder's page list drops everything after " · "
			"page_title": f"{page_type} · {theme_name}",
			"route": f"{ROUTE_PREFIX}/{frappe.scrub(theme_name)}/{PAGE_ROUTES[page_type]}",
			"project_folder": folder,
			"draft_blocks": [ROOT_BLOCK],
			"head_html": HEAD_HTML,
		}
	)
	return page.insert().name
