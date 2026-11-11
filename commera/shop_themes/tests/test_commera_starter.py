import os
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

import commera.sdk
from commera.shop_themes.doctype.shop_theme.shop_theme import render_theme_context
from commera.shop_themes.sections import get_theme_json, validate_layout
from commera.shop_themes.theme_resolver import ThemePageRenderer, build_base_context
from commera.tests.test_localization import use_storefront_languages

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
		frappe.get_doc(
			doctype="Theme Layout",
			name=f"{STARTER}-{page}",
			theme=STARTER,
			page=page,
			published_layout=frappe.as_json(layout),
			modified=frappe.utils.now_datetime(),
		).db_insert()

	def assert_layout_rejected(self, page, section_type):
		layout = {"sections": [{"id": "probe", "type": section_type}]}
		with self.assertRaises(frappe.ValidationError):
			validate_layout(self.theme_context, layout, page)

	def test_the_account_dashboard_lands_on_the_starter_orders_page(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		frappe.local.request = Request(EnvironBuilder(path="/ar/account/dashboard").get_environ())
		renderer = ThemePageRenderer("account/dashboard")
		renderer.theme_dirs = [STARTER_DIR]
		renderer.template_path = "pages/account/dashboard.html"
		renderer.requires_auth = True

		with self.assertRaises(frappe.Redirect):
			renderer.render()
		self.assertEqual(frappe.flags.redirect_location, "/ar/account/orders")

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

	def test_a_wrongly_typed_setting_names_its_section_and_field(self):
		layout = {
			"sections": [
				{"id": "recommendations", "type": "product_recommendations", "settings": {"limit": "6"}}
			]
		}
		with self.assertRaisesRegex(
			frappe.ValidationError, 'Product recommendations section: "Products to show" has the wrong type.'
		):
			validate_layout(self.theme_context, layout)

		layout["sections"][0]["settings"]["limit"] = 6
		validate_layout(self.theme_context, layout)

	def test_the_header_and_footer_come_from_their_group_layouts(self):
		html = self.render_home([])

		self.assertIn('aria-label="Wishlist"', html)
		self.assertIn("grid grid-cols-[1fr_auto_1fr] items-center", html)
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
		self.assertNotIn("grid grid-cols-[1fr_auto_1fr] items-center", html)
		self.assertIn("ZZ Starter copyright", html)
		self.assertIn("ZZ Starter column", html)

	def test_the_header_switches_between_the_published_languages(self):
		use_storefront_languages(self, "en", published=("en", "ar"), unpublished=("fr",))
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		frappe.local.request = Request(EnvironBuilder(path="/ar/", query_string="ref=zz").get_environ())

		html = self.render_home([])

		self.assertIn('aria-label="Language"', html)
		self.assertIn('href="/?ref=zz" hreflang="en"', html)
		self.assertIn('href="/ar?ref=zz" hreflang="ar"', html)
		self.assertNotIn('hreflang="fr"', html)
		self.assertIn('href="/ar/account/', html)
		self.assertNotIn('href="/en', html)

	def test_a_query_cannot_break_out_of_a_header_link(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		query = 'x="><img src=x onerror=alert(1)>'
		frappe.local.request = Request(EnvironBuilder(path="/ar/", query_string=query).get_environ())

		html = self.render_home([])

		self.assertNotIn("<img src=x", html)
		self.assertNotIn("onerror=alert", html)
		self.assertIn('href="/?x=%22%3E%3Cimg', html)

	def test_a_single_language_store_has_no_switcher_and_no_prefixes(self):
		use_storefront_languages(self, "en", published=("en",))
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		frappe.local.request = Request(EnvironBuilder(path="/").get_environ())

		html = self.render_home([])

		self.assertNotIn('aria-label="Language"', html)
		self.assertNotIn('lang="en" dir="ltr" data-language', html)
		self.assertIn('href="/account/', html)
		self.assertNotIn('href="/en', html)

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
