import os
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

import commera.sdk
from commera.shop_themes.doctype.shop_theme.shop_theme import render_theme_context
from commera.shop_themes.sections import LAYOUT_CACHE_PREFIX, get_theme_json, validate_layout
from commera.shop_themes.theme_resolver import ThemePageRenderer, build_base_context

STARTER = "Commera Starter"
STARTER_DIR = os.path.join(frappe.get_app_path("commera"), "themes", "commera_starter")
PRODUCT_CARD = {
	"id": "ZZ-STARTER-CARD",
	"handle": "zz-starter-card",
	"title": "ZZ Starter Linen Shirt",
	"vendor": None,
	"product_type": None,
	"color": None,
	"image": None,
	"hover_image": None,
	"currency": "INR",
	"price": 1999.0,
	"compare_at_price": 2499.0,
	"available": True,
	"rating": {"average": 0, "count": 0},
	"updated_at": None,
}


class IntegrationTestCommeraStarter(IntegrationTestCase):
	def setUp(self):
		self.theme_context = {
			"theme_name": STARTER,
			"theme_type": "Sections",
			"names": [STARTER],
			"dirs": [STARTER_DIR],
			"apps": {STARTER: "commera"},
			"settings_doctype": None,
		}
		for page in ("index", "header_group", "footer_group"):
			frappe.cache.delete_value(f"{LAYOUT_CACHE_PREFIX}{STARTER}:{page}")
			self.addCleanup(frappe.cache.delete_value, f"{LAYOUT_CACHE_PREFIX}{STARTER}:{page}")
		frappe.db.delete("Theme Layout", {"theme": STARTER})

	def render_home(self, products):
		with (
			patch.object(commera.sdk.catalog, "list_products", return_value={"products": products}),
			render_theme_context(self.theme_context),
		):
			renderer = ThemePageRenderer("index")
			renderer.theme_dirs = [STARTER_DIR]
			renderer.template_path = "pages/index.html"
			return renderer.render_with_theme_loader(build_base_context(None))

	def publish(self, page, layout):
		frappe.cache.set_value(f"{LAYOUT_CACHE_PREFIX}{STARTER}:{page}", {"layout": layout})

	def assert_layout_rejected(self, page, section_type):
		layout = {"sections": [{"id": "probe", "type": section_type}]}
		with self.assertRaises(frappe.ValidationError):
			validate_layout(self.theme_context, layout, page)

	def test_every_starter_layout_passes_the_layout_checks(self):
		for page in ("index", "header_group", "footer_group"):
			with self.subTest(page):
				validate_layout(
					self.theme_context, get_theme_json([STARTER_DIR], f"layouts/{page}.json"), page
				)

	def test_sections_are_only_accepted_where_their_schema_allows(self):
		self.assert_layout_rejected("header_group", "hero")
		self.assert_layout_rejected("footer_group", "header")
		self.assert_layout_rejected("index", "header")
		self.assert_layout_rejected("index", "footer")

		newsletter = {"sections": [{"id": "newsletter", "type": "newsletter"}]}
		validate_layout(self.theme_context, newsletter, "index")
		validate_layout(self.theme_context, newsletter, "footer_group")

	def test_the_header_and_footer_come_from_their_group_layouts(self):
		html = self.render_home([])

		self.assertIn('aria-label="Wishlist"', html)
		self.assertIn("grid grid-cols-3 items-center", html)
		self.assertNotIn("ZZ Starter announcement", html)

		self.publish(
			"header_group",
			{
				"sections": [
					{
						"id": "announcement",
						"type": "announcement_bar",
						"settings": {"text": "ZZ Starter announcement"},
					},
					{
						"id": "header",
						"type": "header",
						"settings": {"logo_position": "start", "show_wishlist": False},
					},
				]
			},
		)
		self.publish(
			"footer_group",
			{
				"sections": [
					{
						"id": "footer",
						"type": "footer",
						"settings": {"copyright": "ZZ Starter copyright"},
						"blocks": [
							{"id": "note", "type": "text", "settings": {"heading": "ZZ Starter column"}}
						],
					}
				]
			},
		)
		html = self.render_home([])

		self.assertIn("ZZ Starter announcement", html)
		self.assertNotIn('aria-label="Wishlist"', html)
		self.assertNotIn("grid grid-cols-3 items-center", html)
		self.assertIn("ZZ Starter copyright", html)
		self.assertIn("ZZ Starter column", html)

	def test_the_home_page_renders_every_section_from_the_theme_defaults(self):
		html = self.render_home([PRODUCT_CARD])

		for expected in (
			"Clothes made to be lived in.",
			"/assets/commera/themes/commera_starter/images/banner-banner-media2.webp",
			"New arrivals",
			"ZZ Starter Linen Shirt",
			commera.sdk.format.money(1999, "INR"),
			commera.sdk.format.money(2499, "INR"),
			"Basics",
			"Read the journal",
			"Letters from the studio",
		):
			self.assertIn(expected, html)

	def test_every_starter_block_is_marked_only_in_the_editor_preview(self):
		get_menu = commera.sdk.shop.get_menu
		footer_menu = {"handle": "footer", "title": "Footer", "items": [{"title": "ZZ Help", "items": []}]}
		with (
			patch.object(
				commera.sdk.shop,
				"get_menu",
				new=lambda handle: footer_menu if handle == "footer" else get_menu(handle),
			),
			patch(
				"commera.shop_themes.theme_resolver.get_shop_theme_settings",
				return_value=frappe._dict(instagram_url="https://instagram.com/zz-starter"),
			),
		):
			for page in ("index", "header_group", "footer_group"):
				layout = get_theme_json([STARTER_DIR], f"layouts/{page}.json")
				with self.subTest(page):
					frappe.local.theme_editor_preview = frappe._dict(layouts={page: layout})
					try:
						html = self.render_home([PRODUCT_CARD])
					finally:
						frappe.local.theme_editor_preview = None

					for section in layout["sections"]:
						for block in section.get("blocks") or []:
							if not section.get("hidden"):
								self.assertIn(f'data-commera-block="{block["id"]}"', html)

			self.assertNotIn("data-commera-block", self.render_home([PRODUCT_CARD]))

	def test_featured_products_is_left_out_when_its_source_has_no_products(self):
		html = self.render_home([])

		self.assertNotIn("New arrivals", html)
		self.assertIn("Letters from the studio", html)
