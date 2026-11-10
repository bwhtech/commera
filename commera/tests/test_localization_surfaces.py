import os
import re

import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.localization import StorefrontLanguages, resolve
from commera.migrate import get_private_path_rules
from commera.order_access import get_order_link
from commera.shop_themes.chrome_preview import get_preview_context, get_preview_language
from commera.shop_themes.theme_resolver import build_base_context
from commera.tests.test_localization import use_storefront_languages

APP_ROOT = frappe.get_app_path("commera")
BASE_TEMPLATES = (
	"themes/commera_starter/components/base.html",
	"themes/shop_base_theme/components/base.html",
	"themes/shop_default_theme/components/base.html",
	"templates/layout.html",
)
HTML_TAG = re.compile(r"<html [^>]*>")


class TestRightToLeftLanguages(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "he", "fr"), unpublished=("fa",))
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))

	def visit(self, path):
		frappe.local.request = Request(EnvironBuilder(path=path).get_environ())
		frappe.local.request_cache.clear()

	def test_the_theme_context_takes_the_direction_from_the_language(self):
		self.visit("/he/products")
		self.assertTrue(build_base_context(None).is_rtl)
		self.visit("/fr/products")
		self.assertFalse(build_base_context(None).is_rtl)

	def test_every_base_template_sets_lang_and_dir_from_the_localization(self):
		for language, direction in (("he", "rtl"), ("fr", "ltr")):
			localization = resolve(f"/{language}/")[0]
			for template in BASE_TEMPLATES:
				with self.subTest(template=template, language=language):
					html = render_html_tag(template, localization)
					self.assertIn(f'lang="{language}"', html)
					self.assertIn(f'dir="{direction}"', html)

	def test_a_chrome_preview_reads_the_direction_of_the_previewed_language(self):
		context = get_preview_context(frappe.get_cached_doc("Commera Settings"), "fa")

		self.assertTrue(context.is_rtl)
		self.assertEqual(context.localization.language.code, "fa")

	def test_a_preview_falls_back_to_the_default_for_an_unknown_language(self):
		self.assertEqual(get_preview_language("fa"), "fa")
		self.assertEqual(get_preview_language("ar"), "en")
		self.assertEqual(get_preview_language(None), "en")


class TestLanguageLinks(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "fr"), unpublished=("de",))
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)

	def test_an_order_link_keeps_a_published_language(self):
		order = frappe._dict(name="SO-0001", custom_order_access_key="key")

		frappe.local.lang = "fr"
		self.assertIn("/fr/account/orders/detail?order_id=SO-0001", get_order_link(order))
		frappe.local.lang = "de"
		self.assertIn("/en/account/orders/detail?order_id=SO-0001", get_order_link(order))

	def test_robots_rules_cover_every_published_language(self):
		rules = get_private_path_rules(StorefrontLanguages.load())

		# The default language lives at the root.
		for prefix in ("", "/fr"):
			self.assertIn(f"Disallow: {prefix}/cart\n", rules)
			self.assertIn(f"Disallow: {prefix}/account\n", rules)
		self.assertNotIn("/en/", rules)
		self.assertNotIn("/de/", rules)


def render_html_tag(template, localization):
	"""Render a base template's opening lines, up to its <html> tag, with `localization`."""
	with open(os.path.join(APP_ROOT, template)) as template_file:
		source = template_file.read()
	head = source[: HTML_TAG.search(source).end()]
	# The starter theme also reads `theme` on its <html> tag.
	return frappe.render_template(head, {"localization": localization, "theme": {}})  # nosemgrep: frappe-ssti
