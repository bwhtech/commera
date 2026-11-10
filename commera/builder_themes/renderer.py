import frappe

from commera.builder_themes.pages import PAGE_TYPE_BY_TEMPLATE, get_theme_pages
from commera.shop_themes.doctype.shop_theme.shop_theme import BUILDER_THEME_TYPE, get_render_theme_context
from commera.shop_themes.doctype.shop_theme_settings.shop_theme_settings import get_compiled_routes
from commera.shop_themes.theme_resolver import ThemePageRenderer, apply_route_groups, match_route


class BuilderThemePageRenderer:
	"""Serves the live Builder theme's published page on its storefront route; anything else falls through to
	the parent theme. Builder is imported only in render(), so a site without Builder never loads it."""

	def __init__(self, path, http_status_code=None):
		self.path = path
		self.http_status_code = http_status_code
		self.page = None
		self.match = None

	def can_render(self):
		theme_context = get_render_theme_context()
		if theme_context["theme_type"] != BUILDER_THEME_TYPE:
			return False

		request_path = ThemePageRenderer(self.path).get_request_path()
		route, self.match = match_route(get_compiled_routes()["routes"], request_path)
		page_type = route and PAGE_TYPE_BY_TEMPLATE.get(route["template_path"])
		if not page_type:
			return False

		page = get_theme_pages(theme_context["theme_name"]).get(page_type)
		if not page or not frappe.db.get_value("Builder Page", page, "published"):
			return False
		self.page = page
		return True

	def render(self):
		from builder.builder.doctype.builder_page.builder_page import BuilderPageRenderer

		# The product page reads its handle from form_dict, as on a Builder dynamic route.
		apply_route_groups(self.match, frappe._dict())
		renderer = BuilderPageRenderer(self.path, self.http_status_code)
		renderer.doctype = "Builder Page"
		renderer.docname = self.page
		renderer.validate_access()
		return renderer.render()
