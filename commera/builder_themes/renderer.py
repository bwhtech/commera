import frappe
from frappe.utils import escape_html, get_url

from commera.builder_themes.page_data import get_page_seo
from commera.builder_themes.pages import PAGE_TYPE_BY_TEMPLATE, get_theme_pages, is_builder_installed
from commera.localization import get_localization
from commera.localization.urls import url
from commera.shop_themes.doctype.shop_theme.shop_theme import BUILDER_THEME_TYPE, get_render_theme_context
from commera.shop_themes.theme_resolver import ThemePageRenderer, apply_route_groups, find_theme_page


class BuilderThemePageRenderer:
	"""Serves the live Builder theme's published page on its storefront route, else falls through to the parent
	theme, as it does for every page when Builder is not installed. Builder is imported only in render()."""

	def __init__(self, path, http_status_code=None):
		self.path = path
		self.http_status_code = http_status_code
		self.page = None
		self.page_type = None
		self.request_path = None
		self.match = None

	def can_render(self):
		theme_context = get_render_theme_context()
		if theme_context["theme_type"] != BUILDER_THEME_TYPE or not is_builder_installed():
			return False

		request_path = ThemePageRenderer(self.path).get_request_path()
		found = find_theme_page(request_path, get_localization().language.code)
		page_type = found and PAGE_TYPE_BY_TEMPLATE.get(found[1])
		if not page_type:
			return False
		self.match = found[3]

		page = get_theme_pages(theme_context["theme_name"]).get(page_type)
		if not page or not frappe.db.get_value("Builder Page", page, "published"):
			return False
		self.page = page
		self.page_type = page_type
		self.request_path = request_path
		return True

	def render(self):
		# The product page reads its handle from form_dict, as on a Builder dynamic route.
		if self.match:
			apply_route_groups(self.match, frappe._dict())
		renderer = get_storefront_renderer(self.page_type, url(f"/{self.request_path}"))(
			self.path, self.http_status_code
		)
		renderer.doctype = "Builder Page"
		renderer.docname = self.page
		renderer.validate_access()
		return renderer.render()


def get_storefront_renderer(page_type: str, storefront_path: str):
	"""Builder's renderer with the storefront's head: Builder's own takes the title from the page record and the
	canonical from the route rule's target (/products/details.html), the same for every product."""
	from builder.builder.doctype.builder_page.builder_page import BuilderPageRenderer

	class StorefrontBuilderPageRenderer(BuilderPageRenderer):
		def update_context(self):
			super().update_context()
			seo = get_page_seo(page_type, frappe.form_dict)
			self.context.title = escape_html(seo["title"])
			self.context.metatags = {
				**(self.context.metatags or {}),
				"title": seo["title"],
				"description": seo["description"],
			}
			self.context.disable_indexing = self.context.disable_indexing or seo["noindex"]

		def set_canonical_url(self):
			self.context.canonical_url = get_url(storefront_path)

	return StorefrontBuilderPageRenderer
