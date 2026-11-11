# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

"""Builder themes: a Shop Theme whose home, listing and product pages are Frappe Builder pages."""

import unittest
from urllib.parse import parse_qsl

import frappe

from commera.api.admin.builder_theme import make_theme_live
from commera.builder_themes.agent_context import get_agent_context
from commera.builder_themes.editor import get_theme_bar, publish_theme
from commera.builder_themes.page_data import get_data_for
from commera.builder_themes.pages import (
	HOME,
	PRODUCT_DETAIL,
	PRODUCT_LISTING,
	get_theme_pages,
	is_builder_installed,
)
from commera.builder_themes.renderer import BuilderThemePageRenderer
from commera.builder_themes.theme import create_builder_theme
from commera.localization.urls import url
from commera.tests.test_product_details import ProductDetailPriceTestCase

THEME = "Test Builder Theme"
STARTER_THEME = "Commera Starter"


@unittest.skipUnless(is_builder_installed(), "Frappe Builder is not installed on this site")
class TestBuilderThemes(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.clear_cache)
		self.addCleanup(frappe.form_dict.clear)
		self.handle = self.make_priced_variant("BUILDER", default_rate=100, sale_rate=80)
		self.make_priced_variant("BUILDERTWO", default_rate=50)
		self.theme = create_builder_theme(THEME)
		self.pages = get_theme_pages(THEME)

	def activate(self, theme_name):
		settings = frappe.get_doc("Shop Theme Settings")
		settings.active_theme = theme_name
		settings.save()

	def publish(self, page_type, blocks=None):
		page = frappe.get_doc("Builder Page", self.pages[page_type])
		page.blocks = frappe.as_json(blocks or [{"element": "div", "blockId": "root", "children": []}])
		page.published = 1
		page.save()

	def test_creates_three_empty_pages_in_a_folder(self):
		self.assertEqual(self.theme.theme_type, "Builder")
		self.assertEqual(self.theme.parent_theme, STARTER_THEME)
		self.assertEqual(set(self.pages), {HOME, PRODUCT_LISTING, PRODUCT_DETAIL})
		for page_name in self.pages.values():
			page = frappe.get_doc("Builder Page", page_name)
			self.assertEqual(page.project_folder, THEME)
			self.assertEqual(page.head_html, "{{ commera_builder_head() }}")
			self.assertFalse(page.published)
		detail = frappe.get_doc("Builder Page", self.pages[PRODUCT_DETAIL])
		self.assertEqual(detail.route, "ct/test_builder_theme/products/:route")
		self.assertEqual(detail.page_title, f"{PRODUCT_DETAIL} · {THEME}")

	def test_refuses_a_taken_name(self):
		with self.assertRaises(frappe.ValidationError):
			create_builder_theme(THEME)

	def test_builder_theme_needs_a_parent(self):
		self.theme.parent_theme = None
		with self.assertRaises(frappe.ValidationError):
			self.theme.save()

	def test_builder_page_data_carries_shop_and_page_data(self):
		page = frappe.get_doc("Builder Page", self.pages[HOME])
		data = page.get_page_data()["commera"]
		self.assertEqual(data["shop"]["cart_url"], url("/cart"))
		self.assertTrue(data["featured_products"])
		card = data["featured_products"][0]
		self.assertIsInstance(card["price"], str)
		self.assertTrue(card["url"].startswith(url("/products") + "/"))

	def test_page_outside_every_theme_gets_no_data(self):
		page = frappe.get_doc({"doctype": "Builder Page", "page_title": "Plain"}).insert()
		self.assertEqual(page.get_page_data(), {})
		self.assertIsNone(get_agent_context(page.name))

	def test_product_page_previews_a_sample_and_reads_the_route(self):
		sample = get_data_for(PRODUCT_DETAIL, {})["product"]
		self.assertTrue(sample["title"])

		product = get_data_for(PRODUCT_DETAIL, {"route": self.handle})["product"]
		self.assertEqual(product["url"], url(f"/products/{self.handle}"))
		self.assertIsInstance(product["price"], str)
		# One size: the add-to-cart button adds it without a size picker.
		self.assertFalse(product["has_sizes"])
		self.assertTrue(product["default_variant_id"])

		with self.assertRaises(frappe.PageDoesNotExistError):
			get_data_for(PRODUCT_DETAIL, {"route": "no-such-product"})

	def test_listing_links_toggle_filters_and_pages(self):
		listing = get_data_for(PRODUCT_LISTING, {})
		self.assertEqual(listing["title"], "All products")
		self.assertFalse(listing["has_active_filters"])

		value = listing["filters"][0]["values"][0]
		self.assertFalse(value["is_active"])
		self.assertIn(url("/products") + "?", value["url"])

		query = dict(parse_qsl(value["url"].split("?", 1)[1]))
		filtered = get_data_for(PRODUCT_LISTING, query)
		self.assertTrue(filtered["has_active_filters"])
		self.assertEqual(filtered["active_filters"][0]["url"], url("/products"))

	def test_renderer_serves_only_published_pages_of_the_live_builder_theme(self):
		self.activate(THEME)
		self.assertFalse(BuilderThemePageRenderer("en/products").can_render())

		self.publish(PRODUCT_LISTING)
		self.assertTrue(BuilderThemePageRenderer("en/products").can_render())
		self.assertFalse(BuilderThemePageRenderer("en/cart").can_render())

		self.activate(STARTER_THEME)
		self.assertFalse(BuilderThemePageRenderer("en/products").can_render())

	def test_renderer_binds_product_data(self):
		repeater = {
			"element": "div",
			"blockId": "grid",
			"isRepeaterBlock": True,
			"dataKey": {"key": "commera.products", "type": "key", "comesFrom": "dataScript"},
			"children": [
				{
					"element": "p",
					"blockId": "card",
					"innerHTML": "Product",
					"dataKey": {
						"key": "title",
						"type": "key",
						"property": "innerHTML",
						"comesFrom": "dataScript",
					},
				}
			],
		}
		self.publish(PRODUCT_LISTING, [{"element": "div", "blockId": "root", "children": [repeater]}])
		self.activate(THEME)

		renderer = BuilderThemePageRenderer("en/products")
		self.assertTrue(renderer.can_render())
		html = renderer.render().get_data(as_text=True)
		first_title = get_data_for(PRODUCT_LISTING, {})["products"][0]["title"]
		self.assertIn(frappe.utils.escape_html(first_title), html)
		self.assertIn("commera-builder.js", html)
		self.assertNotIn("noindex", html)

	def test_agent_context_names_the_role_and_the_data(self):
		home = get_agent_context(self.pages[HOME])
		self.assertIn("Home page", home)
		self.assertIn("featured_products", home)
		self.assertIn("commera.product.title", home)
		self.assertIn('"test-builder-theme-"', home)

		detail = get_agent_context(self.pages[PRODUCT_DETAIL])
		self.assertIn(f"Match the theme's Home page ({self.pages[HOME]})", detail)
		self.assertIn("data-commera-add-to-cart", detail)
		self.assertIn("commera:cart-added", detail)

	def test_theme_bar_lists_the_pages_and_preview_choices(self):
		bar = get_theme_bar(self.pages[PRODUCT_DETAIL])
		self.assertEqual(bar["theme"], THEME)
		self.assertFalse(bar["is_live"])
		self.assertEqual([page["label"] for page in bar["pages"]], ["Home", "Listing", "Product"])
		self.assertEqual(bar["preview"]["variable"], "route")
		self.assertIn(self.handle, [option["value"] for option in bar["preview"]["options"]])

		self.assertEqual(get_theme_bar(self.pages[PRODUCT_LISTING])["preview"]["variable"], "category")
		self.assertIsNone(get_theme_bar(self.pages[HOME])["preview"])

	def test_publish_theme_skips_pages_not_built_yet(self):
		page = frappe.get_doc("Builder Page", self.pages[HOME])
		page.draft_blocks = frappe.as_json(
			[{"element": "div", "blockId": "root", "children": [{"element": "p", "blockId": "hello"}]}]
		)
		page.save()

		result = publish_theme(THEME)
		self.assertEqual(result, {"published": ["Home"], "skipped": ["Listing", "Product"]})
		self.assertTrue(frappe.db.get_value("Builder Page", self.pages[HOME], "published"))
		self.assertFalse(frappe.db.get_value("Builder Page", self.pages[PRODUCT_DETAIL], "published"))

	def test_make_theme_live_activates_it(self):
		make_theme_live(THEME)
		self.assertTrue(get_theme_bar(self.pages[HOME])["is_live"])
