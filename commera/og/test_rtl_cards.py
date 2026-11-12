# Copyright (c) 2026, company@bwhstudios.com and contributors
# See license.txt

"""Right-to-left OG cards. Chromium lays them out from `dir` on <html>; these tests read that HTML."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.localization import pin_localization, resolve
from commera.og import generator
from commera.tests.test_localization import use_storefront_languages
from commera.www import og_image_render

PRODUCT_CARD = {
	"store_name": "متجر الخليج",
	"display_name": "حذاء Nike Air Max 270 الرياضي 🔥 (مقاس 42)",
	"brand": "Nike",
	"price": "SAR 499.00",
}
STORE_CARD = {
	"store_name": "متجر الخليج للأحذية",
	"tagline": "أحذية رياضية أصلية",
	"site_host": "shop.example.com",
}


def card_html(template, context, path):
	with pin_localization(resolve(path)[0]):
		return generator.render_card_html(template, context)


class TestRightToLeftCards(IntegrationTestCase):
	def test_an_arabic_card_is_a_right_to_left_page(self):
		use_storefront_languages(self, "en", published=("en", "ar"))

		for template, context in (
			(generator.BUNDLED_CARD_TEMPLATE, PRODUCT_CARD),
			(generator.STORE_CARD_TEMPLATE, STORE_CARD),
		):
			with self.subTest(template):
				html_str = card_html(template, context, "/ar")
				self.assertIn('<html lang="ar" dir="rtl">', html_str)
				self.assertIn(context["store_name"], html_str)

	def test_an_english_card_on_an_arabic_store_is_left_to_right(self):
		use_storefront_languages(self, "ar", published=("ar", "en"))

		self.assertIn('<html lang="ar" dir="rtl">', card_html(generator.BUNDLED_CARD_TEMPLATE, {}, "/"))
		self.assertIn('<html lang="en" dir="ltr">', card_html(generator.BUNDLED_CARD_TEMPLATE, {}, "/en"))

	def test_a_fragment_template_gets_the_direction_too(self):
		use_storefront_languages(self, "en", published=("en", "ar"))

		html_str = card_html("<div>{{ store_name | e }}</div>", PRODUCT_CARD, "/ar")

		self.assertIn('<html lang="ar" dir="rtl">', html_str)
		self.assertIn(f"<div>{PRODUCT_CARD['store_name']}</div>", html_str)

	def test_the_bundled_cards_use_no_physical_left_or_right_for_text(self):
		for template in (generator.BUNDLED_CARD_TEMPLATE, generator.STORE_CARD_TEMPLATE):
			path = frappe.get_app_path("commera", template.removeprefix("commera/"))
			# nosemgrep: frappe-security-file-traversal  # bundled app path, not user input
			with open(path) as template_file:
				source = template_file.read()
			for physical in (
				"margin-left",
				"margin-right",
				"padding-left",
				"padding-right",
				"text-align: left",
			):
				with self.subTest(template=template, physical=physical):
					self.assertNotIn(physical, source)

	def test_a_right_to_left_store_card_has_its_own_cache_file(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.addCleanup(setattr, frappe.local.flags, "redirect_location", None)
		cards = set()
		with (
			patch.object(og_image_render, "build_store_card_html", return_value="<div>Gulf Store</div>"),
			patch.object(og_image_render, "render_card_image", return_value=b"jpg"),
			patch.object(og_image_render, "write_cache"),
		):
			for path in ("/", "/ar"):
				with pin_localization(resolve(path)[0]), self.assertRaises(frappe.Redirect):
					og_image_render.serve_store_card()
				cards.add(frappe.local.flags.redirect_location)
		self.assertEqual(len(cards), 2)
