# Copyright (c) 2026, ivend and Contributors
# Page text that reaches HTML: the body is sanitized on read; titles and SEO text are escaped on render.

from html.parser import HTMLParser

import frappe
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.storefront import shop as storefront_shop
from commera.commera_ecommerce.doctype.shop_web_page.shop_web_page import get_translated_page
from commera.commera_ecommerce.doctype.shop_web_page.test_shop_web_page import (
	ENGLISH_CONTENT,
	PAGE,
	ShopWebPageTestCase,
)
from commera.localization import CURRENT, MISSING, register
from commera.sdk import shop
from commera.shop_themes.doctype.shop_theme.shop_theme import build_theme_context, render_theme_context
from commera.shop_themes.sections import LAYOUT_CACHE_PREFIX
from commera.shop_themes.theme_resolver import ThemePageRenderer
from commera.tests.test_content_translation import use_storefront_language

UNSAFE_BODY = "<p>مرحبا</p><img src=x onerror=alert(1)><script>steal()</script>"
TAG_INJECTION = "</title><script>alert(1)</script>"
ATTRIBUTE_INJECTION = '" onmouseover="alert(1)'
THEMES = ("Shop Default Theme", "Summer Theme", "Commera Starter")


class TestShopWebPageBodySanitizing(ShopWebPageTestCase):
	"""Rows written straight to the database skip the save-time sanitizer."""

	def setUp(self):
		super().setUp()
		self.page = self.make_page()
		# The headless endpoint is rate limited by IP.
		self.addCleanup(setattr, frappe.local, "request_ip", getattr(frappe.local, "request_ip", None))
		frappe.local.request_ip = "127.0.0.1"

	def write_translation(self, field, value):
		name = register(PAGE, self.page.name, field, "ar", "placeholder")
		frappe.db.set_value("Content Translation", name, "translated_value", value)

	def write_page(self, **values):
		frappe.db.set_value(PAGE, self.page.name, values)
		frappe.clear_document_cache(PAGE, self.page.name)

	def assert_sanitized(self, lang):
		use_storefront_language(self, lang)
		bodies = {
			"context": self.run_context(self.page.route, lang=lang).content,
			"sdk": shop.get_page(self.page.route)["body_html"],
			"api": storefront_shop.get_page(self.page.route)["body_html"],
		}
		for source, body in bodies.items():
			with self.subTest(source=source, lang=lang):
				self.assertIn("مرحبا", body)
				self.assertNotIn("onerror", body)
				self.assertNotIn("<script", body)

	def test_a_translation_written_to_the_database_is_sanitized_and_keeps_its_status(self):
		self.write_translation("content", UNSAFE_BODY)
		self.assert_sanitized("ar")
		self.assertEqual(get_translated_page(self.page)["content"].status, CURRENT)

	def test_a_source_body_written_to_the_database_is_sanitized(self):
		self.write_page(content=UNSAFE_BODY)
		self.assert_sanitized("en")

	def test_a_frappe_dictionary_translation_of_the_body_is_sanitized(self):
		translation = frappe.get_doc(
			{
				"doctype": "Translation",
				"language": "ar",
				"source_text": ENGLISH_CONTENT,
				"translated_text": UNSAFE_BODY,
			}
		).insert()
		self.addCleanup(frappe.delete_doc, "Translation", translation.name, force=True)
		self.assert_sanitized("ar")
		self.assertEqual(get_translated_page(self.page)["content"].status, MISSING)


class TestShopWebPageEscaping(ShopWebPageTestCase):
	def setUp(self):
		super().setUp()
		self.page = self.make_page(meta_description=ATTRIBUTE_INJECTION)
		for field, value in (("title", TAG_INJECTION), ("meta_title", ATTRIBUTE_INJECTION)):
			name = register(PAGE, self.page.name, field, "ar", "placeholder")
			frappe.db.set_value("Content Translation", name, "translated_value", value)
		self.saved_form_dict = frappe.local.form_dict
		self.addCleanup(setattr, frappe.local, "form_dict", self.saved_form_dict)

	def test_titles_breadcrumbs_and_seo_text_are_escaped_on_the_www_page(self):
		context = self.run_context(self.page.route, lang="ar")
		html = frappe.render_template("www/shop_web_page/index.html", context)
		self.assert_escaped(html)

	def test_titles_and_seo_text_are_escaped_in_each_bundled_theme(self):
		for theme in THEMES:
			with self.subTest(theme=theme):
				self.assert_escaped(self.render_theme(theme))

	def test_the_starter_heading_matches_the_sdk_title(self):
		register(PAGE, self.page.name, "title", "ar", "سياسة الإرجاع")
		html = self.render_theme("Commera Starter")
		self.assertIn("سياسة الإرجاع</h1>", html)

	def test_the_sdk_keeps_plain_text_unescaped(self):
		use_storefront_language(self, "ar")
		page = shop.get_page(self.page.route)
		self.assertEqual(page["title"], TAG_INJECTION)
		self.assertEqual(page["seo"]["title"], ATTRIBUTE_INJECTION)
		self.assertEqual(page["seo"]["description"], ATTRIBUTE_INJECTION)

	def render_theme(self, theme):
		self.clear_layout_cache(theme)
		path = f"/ar/page/{self.page.route}"
		frappe.local.lang = "ar"
		frappe.local.request = Request(EnvironBuilder(path=path).get_environ())
		frappe.local.form_dict = frappe._dict(route=self.page.route)
		theme_context = build_theme_context(theme)
		with render_theme_context(theme_context):
			renderer = ThemePageRenderer(path.strip("/"))
			renderer.theme_dirs = theme_context["dirs"]
			renderer.template_path = "pages/shop_web_page.html"
			return renderer.render().get_data(as_text=True)

	def clear_layout_cache(self, theme):
		frappe.db.delete("Theme Layout", {"theme": theme})
		for layout in ("page", "header_group", "footer_group"):
			frappe.cache.delete_value(f"{LAYOUT_CACHE_PREFIX}{theme}:{layout}")
			self.addCleanup(frappe.cache.delete_value, f"{LAYOUT_CACHE_PREFIX}{theme}:{layout}")

	def assert_escaped(self, html):
		self.assertNotIn("<script>alert(1)", html)
		self.assertNotIn(ATTRIBUTE_INJECTION, html)
		self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;</h1>", html)
		self.assertIn('content="&#34; onmouseover=&#34;alert(1)"', html)
		self.assertIn("<title>&#34; onmouseover=&#34;alert(1)</title>", html)
		parser = AttributeCollector()
		parser.feed(html)
		self.assertNotIn("onmouseover", parser.attributes)
		self.assertFalse([script for script in parser.scripts if "alert(1)" in script])


class AttributeCollector(HTMLParser):
	"""Every attribute name, and the text of every script that is not JSON-LD."""

	def __init__(self):
		super().__init__()
		self.attributes, self.scripts, self.in_script = set(), [], False

	def handle_starttag(self, tag, attrs):
		self.attributes.update(name for name, _value in attrs)
		self.in_script = tag == "script" and ("type", "application/ld+json") not in attrs

	def handle_endtag(self, tag):
		self.in_script = False

	def handle_data(self, data):
		if self.in_script:
			self.scripts.append(data)
