from unittest.mock import patch

import frappe

import commera.sdk
from commera.localization import register, resolve
from commera.shop_themes.doctype.shop_theme.shop_theme import build_theme_context, render_theme_context
from commera.shop_themes.render import render_themed_template
from commera.shop_themes.sections import LAYOUT_CACHE_PREFIX
from commera.shop_themes.theme_resolver import ThemePageRenderer, build_base_context
from commera.tests.test_store_frame_translation import FOOTER_TEMPLATE, SETTINGS, StoreFrameTestCase
from commera.www import footer_editor_preview, navbar_editor_preview

SUMMER_FOOTER = "components/includes/site_footer.html"
STARTER = "Commera Starter"
UNSAFE_NAME = '" onload="alert(1)<script>alert(2)</script>'
ESCAPED_NAME = "&#34; onload=&#34;alert(1)&lt;script&gt;alert(2)&lt;/script&gt;"
ARABIC_NAME = "بيت الكتان"


class TestStoreFrameRendering(StoreFrameTestCase):
	def setUp(self):
		super().setUp()
		self.arabic = resolve("/ar")[0]
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)

	def write_unsafe_name(self):
		"""Straight to the database: saving a translation strips tags, a direct write does not."""
		name = register(SETTINGS, SETTINGS, "store_name", "ar", "placeholder")
		frappe.db.set_value("Content Translation", name, "translated_value", UNSAFE_NAME)

	def assert_name_escaped(self, html):
		self.assertNotIn("<script>alert(2)", html)
		self.assertNotIn('" onload="', html)
		self.assertIn(f'alt="{ESCAPED_NAME}', html)
		self.assertIn(f"{ESCAPED_NAME}. All Rights Reserved", html)

	def test_both_footers_escape_a_translated_shop_name(self):
		self.write_unsafe_name()
		context = {"localization": self.arabic}
		footers = {
			"default": frappe.render_template(FOOTER_TEMPLATE, context),
			"summer": render_themed_template(SUMMER_FOOTER, context, theme_name="Summer Theme"),
		}
		for footer, html in footers.items():
			with self.subTest(footer=footer):
				self.assert_name_escaped(html)

	def test_the_starter_shows_the_translated_shop_name_everywhere(self):
		html = self.render_starter_home("ar")

		self.assertRegex(html, rf'tracking-widest">\s*{ARABIC_NAME}\s*</a>')
		self.assertIn(f'tracking-widest">{ARABIC_NAME}</span>', html)
		self.assertIn(f'tracking-widest">{ARABIC_NAME}</p>', html)
		self.assertIn(f"© {frappe.utils.getdate().year} {ARABIC_NAME}</p>", html)

	def test_the_starter_escapes_a_translated_shop_name(self):
		self.write_unsafe_name()
		html = self.render_starter_home("ar")

		self.assertNotIn("<script>alert(2)", html)
		self.assertIn(f'tracking-widest">{ESCAPED_NAME}</p>', html)

	def test_the_starter_falls_back_to_the_app_name_without_a_store_name(self):
		frappe.db.set_single_value(SETTINGS, "store_name", "")
		frappe.clear_document_cache(SETTINGS, SETTINGS)
		context = build_base_context(None)

		self.assertTrue(context.app_name)
		self.assertEqual(context.shop_name, context.app_name)

	def test_the_navbar_preview_shows_the_header_in_the_preview_language(self):
		html = self.render_preview(navbar_editor_preview, lang="ar")

		self.assertIn(ARABIC_NAME, html)
		self.assertNotIn("Linen House", html)

	def test_the_footer_preview_translates_a_saved_shop_name(self):
		html = self.render_preview(footer_editor_preview, lang="ar", store_name="Linen House")

		self.assertIn(ARABIC_NAME, html)
		self.assertNotIn("Linen House", html)

	def test_the_footer_preview_shows_an_unsaved_shop_name_as_typed(self):
		html = self.render_preview(footer_editor_preview, lang="ar", store_name="Linen & Loom")

		self.assertIn("Linen &amp; Loom", html)
		self.assertNotIn("&amp;amp;", html)
		self.assertNotIn(ARABIC_NAME, html)

	def render_preview(self, page, **form):
		frappe.local.form_dict = frappe._dict(form)
		context = frappe._dict()
		page.get_context(context)
		return context.rendered_html

	def render_starter_home(self, language):
		self.serve(language)
		frappe.local.lang = language
		for page in ("index", "header_group", "footer_group"):
			frappe.cache.delete_value(f"{LAYOUT_CACHE_PREFIX}{STARTER}:{page}")
		theme_context = build_theme_context(STARTER)
		with (
			patch.object(commera.sdk.catalog, "list_products", return_value={"products": []}),
			render_theme_context(theme_context),
		):
			renderer = ThemePageRenderer("index")
			renderer.theme_dirs = theme_context["dirs"]
			renderer.template_path = "pages/index.html"
			return renderer.render_with_theme_loader(build_base_context(None))
