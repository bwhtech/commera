# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

import copy

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.jinja import get_jenv

from commera.api.admin.theme import activate_theme
from commera.api.admin.theme_layout import discard, get_editor, publish, save_draft
from commera.shop_themes.doctype.shop_theme.shop_theme import get_render_theme_context
from commera.shop_themes.sections import clear_layout_cache
from commera.shop_themes.theme_resolver import get_theme_environment

SUMMER_THEME = "Summer Theme"
CLASSIC_THEME = "Shop Default Theme"


class TestAdminThemeLayout(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(clear_layout_cache, SUMMER_THEME, "index")
		self.addCleanup(frappe.clear_cache)
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")

		frappe.db.delete("Theme Layout", {"theme": SUMMER_THEME, "page": "index"})
		clear_layout_cache(SUMMER_THEME, "index")
		self.file_layout = get_editor(SUMMER_THEME)["theme_file_layout"]

	def edited_layout(self, heading):
		layout = copy.deepcopy(self.file_layout)
		layout["sections"][0]["blocks"][0]["settings"]["heading"] = heading
		return layout

	def render_home_layout(self):
		activate_theme(SUMMER_THEME)
		theme_environment = get_theme_environment(get_jenv(), get_render_theme_context()["dirs"])
		return theme_environment.from_string("{{ render_layout('index') }}").render()

	def test_get_editor_says_whether_the_theme_is_live(self):
		activate_theme(SUMMER_THEME)
		self.assertTrue(get_editor(SUMMER_THEME)["live"])

		activate_theme(CLASSIC_THEME)
		self.assertFalse(get_editor(SUMMER_THEME)["live"])

	def test_get_editor_opens_the_theme_file_layout_when_nothing_is_saved(self):
		editor = get_editor(SUMMER_THEME, "index")

		self.assertEqual(editor["theme_type"], "Sections")
		self.assertIn("index", editor["pages"])
		self.assertIsNone(editor["published_layout"])
		self.assertFalse(editor["has_unpublished_changes"])
		self.assertEqual(editor["draft_layout"], editor["theme_file_layout"])
		self.assertEqual(editor["settings"]["doctype"], "Summer Theme Settings")

		schemas = {schema["type"]: schema for schema in editor["section_schemas"]}
		self.assertEqual(schemas["hero_slider"]["category"], "Banners")
		self.assertIn("slide", schemas["hero_slider"]["blocks"])
		for section in editor["theme_file_layout"]["sections"]:
			self.assertIn(section["type"], schemas)

	def test_save_draft_round_trips_without_touching_the_live_layout(self):
		layout = self.edited_layout("ZZ Draft Heading")

		saved = save_draft(SUMMER_THEME, "index", frappe.as_json(layout))

		self.assertEqual(saved["draft_layout"], layout)
		self.assertIsNone(saved["published_layout"])
		self.assertTrue(saved["has_unpublished_changes"])
		self.assertEqual(get_editor(SUMMER_THEME)["draft_layout"], layout)
		self.assertNotIn("ZZ Draft Heading", self.render_home_layout())

	def test_save_draft_refuses_a_layout_the_theme_cannot_render(self):
		layout = copy.deepcopy(self.file_layout)
		layout["sections"].append({"id": "zz-ghost", "type": "no_such_section"})

		self.assertRaises(frappe.ValidationError, save_draft, SUMMER_THEME, "index", layout)
		self.assertFalse(frappe.db.exists("Theme Layout", {"theme": SUMMER_THEME, "page": "index"}))

	def test_publish_changes_what_the_storefront_renders(self):
		layout = self.edited_layout("ZZ Published Heading")

		published = publish(SUMMER_THEME, "index", layout)

		self.assertEqual(published["published_layout"], layout)
		self.assertFalse(published["has_unpublished_changes"])
		self.assertIn("ZZ Published Heading", self.render_home_layout())

	def test_discard_restores_the_published_layout(self):
		published_layout = self.edited_layout("ZZ Published Heading")
		publish(SUMMER_THEME, "index", published_layout)
		save_draft(SUMMER_THEME, "index", self.edited_layout("ZZ Draft Heading"))

		discarded = discard(SUMMER_THEME, "index")

		self.assertEqual(discarded["draft_layout"], published_layout)
		self.assertFalse(discarded["has_unpublished_changes"])

	def test_discard_restores_the_theme_file_layout_when_never_published(self):
		save_draft(SUMMER_THEME, "index", self.edited_layout("ZZ Draft Heading"))

		discarded = discard(SUMMER_THEME, "index")

		self.assertEqual(discarded["draft_layout"], self.file_layout)
		self.assertFalse(discarded["has_unpublished_changes"])

	def test_a_classic_theme_has_no_layouts_to_edit(self):
		self.assertRaises(frappe.ValidationError, get_editor, CLASSIC_THEME)
		self.assertRaises(frappe.ValidationError, save_draft, CLASSIC_THEME, "index", self.file_layout)

	def test_a_page_the_theme_ships_no_layout_for_is_refused(self):
		self.assertRaises(frappe.ValidationError, get_editor, SUMMER_THEME, "zz-no-such-page")

	def test_only_store_managers_reach_the_editor(self):
		frappe.set_user("Guest")

		self.assertRaises(frappe.PermissionError, get_editor, SUMMER_THEME)
		self.assertRaises(frappe.PermissionError, save_draft, SUMMER_THEME, "index", self.file_layout)
		self.assertRaises(frappe.PermissionError, publish, SUMMER_THEME, "index", self.file_layout)
		self.assertRaises(frappe.PermissionError, discard, SUMMER_THEME, "index")
