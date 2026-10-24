# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

"""The dashboard Theme API, and the storefront preview the theme editor frames."""

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin.theme import (
	activate_theme,
	build_editor_data,
	get_editor_data,
	save_theme_settings,
)
from commera.shop_themes.tests.theme_fixtures import FIXTURE_THEME_NAME, ThemeFixtureMixin
from commera.www import theme_editor_preview

SUMMER_THEME = "Summer Theme"
BASE_THEME = "Shop Base Theme"
DEFAULT_THEME = "Shop Default Theme"


class TestAdminTheme(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.clear_cache)

		activate_theme(SUMMER_THEME)

	def find_theme(self, themes, name):
		return next((theme for theme in themes if theme["name"] == name), None)

	def field_labels(self, groups):
		return [field["fieldname"] for group in groups for field in group["fields"]]

	def test_editor_data_names_the_live_theme_and_lists_the_rest(self):
		data = get_editor_data()

		self.assertEqual(data["active_theme"], SUMMER_THEME)
		self.assertTrue(self.find_theme(data["themes"], SUMMER_THEME)["live"])
		self.assertFalse(self.find_theme(data["themes"], BASE_THEME)["live"])
		# Live first: the screen leads with the theme the storefront is actually serving.
		self.assertTrue(data["themes"][0]["live"])

	def test_editor_data_renders_the_live_themes_own_settings(self):
		data = get_editor_data()

		self.assertEqual(data["settings"]["doctype"], "Summer Theme Settings")
		self.assertIn("categories_title", self.field_labels(data["settings"]["groups"]))
		# A table is rows, not a field: it is reported so the screen can link out to it.
		self.assertNotIn("hero_slides", self.field_labels(data["settings"]["groups"]))
		self.assertIn("hero_slides", [table["fieldname"] for table in data["settings"]["child_tables"]])

	def test_a_theme_without_settings_reports_none_rather_than_failing(self):
		activate_theme(BASE_THEME)

		data = build_editor_data()
		self.assertIsNone(data["settings"]["doctype"])
		self.assertEqual(data["settings"]["groups"], [])

	def test_activate_theme_switches_the_storefront(self):
		data = activate_theme(BASE_THEME)

		self.assertEqual(data["active_theme"], BASE_THEME)
		self.assertEqual(frappe.db.get_single_value("Shop Theme Settings", "active_theme"), BASE_THEME)

	def test_activate_theme_refuses_a_theme_that_is_not_installed(self):
		self.assertRaises(frappe.ValidationError, activate_theme, "ZZ No Such Theme")

	def test_save_theme_settings_writes_the_live_themes_single(self):
		data = save_theme_settings(categories_title="ZZ Categories")

		self.assertEqual(
			frappe.db.get_single_value("Summer Theme Settings", "categories_title"), "ZZ Categories"
		)
		# The write answers with the whole screen, so the editor never renders a stale value.
		saved = next(
			field
			for group in data["settings"]["groups"]
			for field in group["fields"]
			if field["fieldname"] == "categories_title"
		)
		self.assertEqual(saved["value"], "ZZ Categories")

	def test_save_theme_settings_refuses_a_field_the_screen_does_not_render(self):
		# hero_slides is a child table: writing rows through a field save would silently drop them.
		self.assertRaises(frappe.ValidationError, save_theme_settings, hero_slides="oops")

	def test_save_theme_settings_refuses_a_field_of_another_doctype(self):
		# Every theme owns its own settings: a field off some other Single is not this screen's to write.
		self.assertRaises(frappe.ValidationError, save_theme_settings, store_name="ZZ Store")


class TestThemeEditorPreview(ThemeFixtureMixin, IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.clear_cache)
		frappe.set_user("Administrator")
		activate_theme(SUMMER_THEME)

	def render(self, lang="en", theme=None):
		# frappe.local, never frappe.form_dict: rebinding the module attribute swaps the LocalProxy out
		# for a plain dict, and every later test in the run reads that stale one.
		frappe.local.form_dict = frappe._dict(lang=lang, theme=theme)
		context = frappe._dict()
		theme_editor_preview.get_context(context)
		return context.rendered_html

	def test_the_pane_frames_the_live_themes_own_home_page(self):
		html = self.render()

		self.assertIn("theme-summer", html)
		# Tracking is blanked: an editor pane must never emit a page view or a second canonical.
		self.assertNotIn("application/ld+json", html)
		self.assertNotIn('rel="canonical"', html)

	def test_a_theme_with_no_home_page_says_so_instead_of_framing_a_404(self):
		self.add_fixture_theme()
		activate_theme(FIXTURE_THEME_NAME)

		self.assertIn("no home page to preview", self.render())

	def test_the_pane_frames_a_theme_that_is_not_live(self):
		html = self.render(theme=DEFAULT_THEME)

		# Its own body class and its own assets, while Summer is the theme the storefront serves:
		# the template helpers must follow the previewed theme, not the live one.
		self.assertIn("theme-shop-default", html)
		self.assertIn("themes/shop_default_theme", html)
		self.assertNotIn("theme-summer", html)

	def test_previewing_a_theme_leaves_the_live_one_alone(self):
		self.render(theme=DEFAULT_THEME)

		self.assertEqual(frappe.db.get_single_value("Shop Theme Settings", "active_theme"), SUMMER_THEME)
		# The pin is scoped to the render: the next preview is the live theme again.
		self.assertIn("theme-summer", self.render())

	def test_a_theme_that_is_not_installed_falls_back_to_the_live_one(self):
		self.assertIn("theme-summer", self.render(theme="ZZ No Such Theme"))

	def test_a_previewed_theme_with_no_home_page_is_named_in_the_message(self):
		self.add_fixture_theme()
		html = self.render(theme=FIXTURE_THEME_NAME)

		self.assertIn(FIXTURE_THEME_NAME, html)
		self.assertIn("no home page to preview", html)
