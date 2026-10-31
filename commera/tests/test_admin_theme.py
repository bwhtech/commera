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
from commera.shop_themes.doctype.shop_theme.shop_theme import build_theme_context
from commera.shop_themes.sections import clear_layout_cache, get_section, get_section_schema
from commera.www import theme_editor_preview

SUMMER_THEME = "Summer Theme"
STARTER_THEME = "Commera Starter"
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
		self.assertEqual(self.find_theme(data["themes"], SUMMER_THEME)["theme_type"], "Sections")
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


def hero_layout(caption, hidden=False, section_id="hero"):
	return {
		"sections": [
			{
				"id": section_id,
				"type": "hero_slider",
				"hidden": hidden,
				"settings": {"caption": caption},
				"blocks": [{"id": "slide-1", "type": "slide", "settings": {"heading": "Slide heading"}}],
			}
		]
	}


class TestThemeEditorPreview(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.clear_cache)
		frappe.set_user("Administrator")
		activate_theme(SUMMER_THEME)

	def render(self, lang="en", theme=None, **form):
		# frappe.local, never frappe.form_dict: rebinding the module attribute swaps the LocalProxy out
		# for a plain dict, and every later test in the run reads that stale one.
		frappe.local.form_dict = frappe._dict(lang=lang, theme=theme, **form)
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
		activate_theme(BASE_THEME)

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
		html = self.render(theme=BASE_THEME)

		self.assertIn(BASE_THEME, html)
		self.assertIn("no home page to preview", html)

	def publish_layout(self, layout):
		self.addCleanup(clear_layout_cache, SUMMER_THEME, "index")
		name = frappe.db.exists("Theme Layout", {"theme": SUMMER_THEME, "page": "index"})
		theme_layout = (
			frappe.get_doc("Theme Layout", name)
			if name
			else frappe.new_doc("Theme Layout", theme=SUMMER_THEME, page="index")
		)
		theme_layout.update(
			{"draft_layout": frappe.as_json(layout), "published_layout": frappe.as_json(layout)}
		)
		theme_layout.save()

	def test_a_posted_layout_renders_in_place_of_the_published_one(self):
		self.publish_layout(hero_layout("Published caption"))

		html = self.render(layout=frappe.as_json(hero_layout("Draft caption")))

		self.assertIn("Draft caption", html)
		self.assertNotIn("Published caption", html)
		self.assertIn("Published caption", self.render())

	def test_a_hidden_section_in_the_posted_layout_is_skipped(self):
		layout = hero_layout("Hidden caption", hidden=True)
		layout["sections"] += hero_layout("Shown caption", section_id="hero-2")["sections"]

		html = self.render(layout=frappe.as_json(layout))

		self.assertNotIn("Hidden caption", html)
		self.assertIn("Shown caption", html)

	def test_the_editor_preview_marks_sections_and_loads_its_script(self):
		html = self.render(layout=frappe.as_json(hero_layout("Draft caption")))

		self.assertIn('<div data-commera-group="index" data-commera-section="hero">', html)
		self.assertIn("/assets/commera/js/theme_editor_preview.js", html)

	def test_the_published_preview_and_the_live_home_page_carry_no_markers(self):
		self.render(layout=frappe.as_json(hero_layout("Draft caption")))

		for html in (self.render(), self.render_live_home_page()):
			self.assertIn("theme-summer", html)
			self.assertNotIn("data-commera-section", html)
			self.assertNotIn("theme_editor_preview.js", html)

	def render_live_home_page(self):
		from frappe.website.serve import get_response_content

		frappe.set_user("Guest")
		frappe.local.form_dict = frappe._dict()
		return get_response_content("/en")

	def test_blocks_get_escaped_editor_attributes_only_in_editor_mode(self):
		theme_context = build_theme_context(SUMMER_THEME)
		schema = get_section_schema(theme_context["dirs"], "hero_slider")
		saved_section = hero_layout("Caption")["sections"][0]
		saved_section["blocks"][0]["id"] = 'slide"><b>'

		editor_block = get_section(schema, saved_section, theme_context, editor_mode=True).blocks[0]
		live_block = get_section(schema, saved_section, theme_context).blocks[0]

		self.assertEqual(str(editor_block.editor_attributes), ' data-commera-block="slide&#34;&gt;&lt;b&gt;"')
		self.assertEqual(str(live_block.editor_attributes), "")

	def test_only_managers_get_the_preview(self):
		frappe.set_user("Guest")

		self.assertRaises(frappe.PermissionError, self.render, layout=frappe.as_json(hero_layout("Draft")))

	def test_a_page_the_theme_ships_no_layout_for_is_rejected(self):
		for page in ("no_such_page", "../index"):
			self.assertRaises(frappe.DoesNotExistError, self.render, page=page)

	def test_a_layout_that_is_not_an_object_with_sections_is_rejected(self):
		for layout in ("[]", '{"sections": "hero"}'):
			self.assertRaises(frappe.ValidationError, self.render, layout=layout)


def announcement_layout(text):
	return {"sections": [{"id": "announcement", "type": "announcement_bar", "settings": {"text": text}}]}


def starter_hero_layout(heading):
	return {"sections": [{"id": "hero", "type": "hero", "settings": {"heading": heading}}]}


def newsletter_layout(heading):
	return {"sections": [{"id": "newsletter", "type": "newsletter", "settings": {"heading": heading}}]}


class TestThemeEditorGroupPreview(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.clear_cache)
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user("Administrator")
		if not frappe.db.exists("Shop Theme", STARTER_THEME):
			frappe.get_doc(
				doctype="Shop Theme",
				name=STARTER_THEME,
				theme_name=STARTER_THEME,
				theme_type="Sections",
				module="Shop Themes",
			).db_insert()
		frappe.db.delete("Theme Layout", {"theme": STARTER_THEME})
		for page in ("index", "header_group", "footer_group"):
			clear_layout_cache(STARTER_THEME, page)
			self.addCleanup(clear_layout_cache, STARTER_THEME, page)
		activate_theme(STARTER_THEME)

	def render(self, **form):
		frappe.local.form_dict = frappe._dict(lang="en", theme=STARTER_THEME, **form)
		context = frappe._dict()
		theme_editor_preview.get_context(context)
		return context.rendered_html

	def publish_layout(self, page, layout):
		frappe.new_doc(
			"Theme Layout",
			theme=STARTER_THEME,
			page=page,
			draft_layout=frappe.as_json(layout),
			published_layout=frappe.as_json(layout),
		).insert()
		clear_layout_cache(STARTER_THEME, page)

	def test_a_header_group_draft_renders_in_the_header_and_not_on_the_live_page(self):
		self.publish_layout("header_group", announcement_layout("Published announcement"))

		html = self.render(header_group_layout=frappe.as_json(announcement_layout("Draft announcement")))

		self.assertIn("Draft announcement", html)
		self.assertNotIn("Published announcement", html)
		self.assertLess(html.index("Draft announcement"), html.index('data-commera-group="index"'))
		for published_html in (self.render(), self.render_live_home_page()):
			self.assertIn("Published announcement", published_html)
			self.assertNotIn("Draft announcement", published_html)

	def test_page_and_group_drafts_apply_together(self):
		html = self.render(
			layout=frappe.as_json(starter_hero_layout("Draft hero")),
			header_group_layout=frappe.as_json(announcement_layout("Draft announcement")),
			footer_group_layout=frappe.as_json(newsletter_layout("Draft newsletter")),
		)

		self.assertIn('<div data-commera-group="header_group" data-commera-section="announcement">', html)
		self.assertIn('<div data-commera-group="footer_group" data-commera-section="newsletter">', html)
		self.assertIn('<div data-commera-group="index" data-commera-section="hero">', html)
		for text in ("Draft announcement", "Draft hero", "Draft newsletter"):
			self.assertIn(text, html)

	def test_a_group_left_out_of_the_post_renders_as_published(self):
		self.publish_layout("header_group", announcement_layout("Published announcement"))

		html = self.render(footer_group_layout=frappe.as_json(newsletter_layout("Draft newsletter")))

		self.assertIn("Published announcement", html)
		self.assertIn('<div data-commera-group="header_group" data-commera-section="announcement">', html)
		self.assertIn("Draft newsletter", html)

	def test_only_the_editor_preview_carries_group_markers(self):
		self.publish_layout("header_group", announcement_layout("Published announcement"))
		self.assertIn(
			'data-commera-group="footer_group"',
			self.render(header_group_layout=frappe.as_json(announcement_layout("Draft announcement"))),
		)

		for html in (self.render(), self.render_live_home_page()):
			self.assertIn("Published announcement", html)
			self.assertNotIn("data-commera-group", html)
			self.assertNotIn("data-commera-section", html)

	def test_a_group_layout_that_is_not_an_object_with_sections_is_rejected(self):
		self.assertRaises(frappe.ValidationError, self.render, footer_group_layout='{"sections": "footer"}')

	def render_live_home_page(self):
		from frappe.website.serve import get_response_content

		frappe.set_user("Guest")
		frappe.local.form_dict = frappe._dict()
		return get_response_content("/en")
