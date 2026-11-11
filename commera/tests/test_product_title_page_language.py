"""The product page's <title> and breadcrumb show the product title in the page language, on every theme."""

import json
import re
from html import escape

import frappe

from commera.api.admin.theme import activate_theme
from commera.localization import register
from commera.tests.test_legacy_title_readers import render_page
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_product_details import ProductDetailPriceTestCase

PRODUCT = "Style Attribute Variant"
THEMES = ("Shop Default Theme", "Summer Theme", "Commera Starter")
ARABIC_TITLE = "قميص & كتان"
NAV = re.compile(r"<nav\b[^>]*>.*?</nav>", re.DOTALL)
TITLE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
JSON_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


class TestProductTitlePageLanguage(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.route = self.make_priced_variant("PAGETITLE", default_rate=30)
		self.product = frappe.get_doc(PRODUCT, {"route": self.route})

	def test_the_arabic_page_shows_the_translated_title_in_title_and_breadcrumb(self):
		register(PRODUCT, self.product.name, "display_name", "ar", ARABIC_TITLE)
		for theme in THEMES:
			with self.subTest(theme):
				activate_theme(theme)
				self.assert_page_title(f"/ar/products/{self.route}", ARABIC_TITLE)

	def test_content_title_matching_a_ui_key_is_not_translated_again(self):
		register(PRODUCT, self.product.name, "display_name", "ar", "Size")
		self.assertNotEqual(frappe._("Size", lang="ar"), "Size")
		for theme in THEMES:
			with self.subTest(theme):
				activate_theme(theme)
				html = self.assert_page_title(f"/ar/products/{self.route}", "Size")
				blocks = [json.loads(block) for block in JSON_LD.findall(html)]
				[product] = [block for block in blocks if block.get("@type") == "Product"]
				self.assertEqual(product["name"], "Size")
				self.assertNotIn(escape(frappe._("Size", lang="ar")), get_breadcrumb(html))
				self.assertIn("الرئيسية", get_breadcrumb(html))
				if theme != "Commera Starter":
					self.assertIn("المنتجات", get_breadcrumb(html))

	def test_the_arabic_page_falls_back_to_the_source_title_without_a_translation(self):
		for theme in THEMES:
			with self.subTest(theme):
				activate_theme(theme)
				self.assert_page_title(f"/ar/products/{self.route}", self.product.display_name)

	def test_the_english_page_keeps_the_source_title(self):
		register(PRODUCT, self.product.name, "display_name", "ar", ARABIC_TITLE)
		for theme in THEMES:
			with self.subTest(theme):
				activate_theme(theme)
				html = self.assert_page_title(f"/products/{self.route}", self.product.display_name)
				self.assertNotIn(escape(ARABIC_TITLE), html)

	def test_the_arabic_product_list_title_is_translated(self):
		for theme in THEMES:
			with self.subTest(theme):
				activate_theme(theme)
				html = render_page(self, "/ar/products")
				self.assertIn("المنتجات", get_title(html))
				self.assertNotIn("Products", get_title(html))

	def assert_page_title(self, path, title):
		html = render_page(self, path)
		self.assertIn(escape(title), get_title(html))
		self.assertIn(escape(title), get_breadcrumb(html))
		self.assertEqual(get_breadcrumb_json_ld(html)[-1]["name"], title)
		other = self.product.display_name if title != self.product.display_name else ARABIC_TITLE
		self.assertNotIn(escape(other), get_title(html) + get_breadcrumb(html))
		return html


def get_title(html):
	return TITLE.search(html).group(1)


def get_breadcrumb(html):
	"""The breadcrumb nav: marked by a breadcrumb class or label, or by its current-page item."""
	[nav] = [nav for nav in NAV.findall(html) if "breadcrumb" in nav.lower() or 'aria-current="page"' in nav]
	return nav


def get_breadcrumb_json_ld(html):
	blocks = [json.loads(block) for block in JSON_LD.findall(html)]
	items = [item for block in blocks for item in (block if isinstance(block, list) else [block])]
	[breadcrumb] = [item for item in items if item.get("@type") == "BreadcrumbList"]
	return breadcrumb["itemListElement"]
