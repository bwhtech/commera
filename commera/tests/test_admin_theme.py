# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

"""The dashboard Theme API, and the storefront preview the theme editor frames."""

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin.pages import save_page
from commera.api.admin.theme import (
	activate_theme,
	build_editor_data,
	get_editor_data,
	save_theme_settings,
)
from commera.api.admin.theme_layout import get_editor, get_preview_entries
from commera.shop_themes.doctype.shop_theme.shop_theme import build_theme_context
from commera.shop_themes.layout_cache import clear_layout_cache
from commera.shop_themes.sections import (
	get_section,
	get_section_schema,
	get_theme_json,
)
from commera.tests.test_product_details import ProductDetailPriceTestCase
from commera.www import theme_editor_preview

SUMMER_THEME = "Summer Theme"
STARTER_THEME = "Commera Starter"
BASE_THEME = "Shop Base Theme"
DEFAULT_THEME = "Shop Default Theme"


STARTER_LAYOUT_PAGES = ("index", "product", "products", "search", "page")


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
		data = save_theme_settings(SUMMER_THEME, categories_title="ZZ Categories")

		self.assertEqual(
			frappe.db.get_single_value("Summer Theme Settings", "categories_title"), "ZZ Categories"
		)
		saved = next(
			field
			for group in data["groups"]
			for field in group["fields"]
			if field["fieldname"] == "categories_title"
		)
		self.assertEqual(saved["value"], "ZZ Categories")

	def test_save_theme_settings_writes_the_edited_theme_not_the_live_one(self):
		live_title = frappe.db.get_single_value("Summer Theme Settings", "categories_title")

		data = save_theme_settings(STARTER_THEME, instagram_url="https://instagram.com/zz")

		self.assertEqual(data["doctype"], "Commera Starter Settings")
		self.assertEqual(
			frappe.db.get_single_value("Commera Starter Settings", "instagram_url"),
			"https://instagram.com/zz",
		)
		self.assertEqual(frappe.db.get_single_value("Summer Theme Settings", "categories_title"), live_title)
		self.assertRaises(
			frappe.ValidationError, save_theme_settings, STARTER_THEME, categories_title="ZZ Categories"
		)

	def test_save_theme_settings_refuses_a_theme_without_settings(self):
		self.assertRaises(frappe.ValidationError, save_theme_settings, BASE_THEME, categories_title="ZZ")

	def test_save_theme_settings_needs_write_on_the_themes_settings(self):
		frappe.set_user("Guest")
		self.assertRaises(
			frappe.PermissionError,
			save_theme_settings,
			STARTER_THEME,
			instagram_url="https://instagram.com/zz",
		)

	def test_save_theme_settings_refuses_a_field_the_screen_does_not_render(self):
		# hero_slides is a child table: writing rows through a field save would silently drop them.
		self.assertRaises(frappe.ValidationError, save_theme_settings, SUMMER_THEME, hero_slides="oops")

	def test_save_theme_settings_refuses_a_field_of_another_doctype(self):
		# Every theme owns its own settings: a field off some other Single is not this screen's to write.
		self.assertRaises(frappe.ValidationError, save_theme_settings, SUMMER_THEME, store_name="ZZ Store")


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
		return get_response_content("/")

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
		return get_response_content("/")


class TestThemeEditorLayoutPagePreview(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.clear_cache)
		self.addCleanup(frappe.db.rollback)
		frappe.set_user("Administrator")
		frappe.db.delete("Theme Layout", {"theme": STARTER_THEME})
		for page in STARTER_LAYOUT_PAGES:
			clear_layout_cache(STARTER_THEME, page)
			self.addCleanup(clear_layout_cache, STARTER_THEME, page)
		activate_theme(STARTER_THEME)

	def render(self, page, layout=None, entry=None):
		frappe.local.form_dict = frappe._dict(
			lang="en", theme=STARTER_THEME, page=page, layout=layout, entry=entry
		)
		context = frappe._dict()
		theme_editor_preview.get_context(context)
		return context.rendered_html

	def starter_layout(self, page):
		return frappe.as_json(
			get_theme_json(build_theme_context(STARTER_THEME)["dirs"], f"layouts/{page}.json")
		)

	def test_each_starter_layout_renders_its_own_page(self):
		route = self.make_priced_variant("PREVIEW", default_rate=40)
		save_page(
			title="ZZ Preview Page", content="<p>Preview page body</p>", route="zz-preview-page", published=1
		)

		for page in STARTER_LAYOUT_PAGES:
			with self.subTest(page=page):
				html = self.render(page, layout=self.starter_layout(page))

				self.assertIn(f'data-commera-group="{page}"', html)
				for other_page in set(STARTER_LAYOUT_PAGES) - {page}:
					self.assertNotIn(f'data-commera-group="{other_page}"', html)

		self.assertIn(f"Display {route}", self.render("product"))
		self.assertIn("Preview page body", self.render("page"))

	def test_the_preview_leaves_the_editors_own_request_form_alone(self):
		self.make_priced_variant("FORM", default_rate=40)

		self.render("product")

		self.assertEqual(frappe.form_dict.page, "product")
		self.assertIsNone(frappe.form_dict.get("route"))

	def test_a_page_with_nothing_to_show_says_so_instead_of_framing_a_404(self):
		frappe.db.set_value("Style Attribute Variant", {"is_published": 1}, "is_published", 0)
		frappe.db.set_value("Shop Web Page", {"published": 1}, "published", 0)

		self.assertIn("Publish a product to preview the product page.", self.render("product"))
		self.assertIn("Publish a product to preview the search page.", self.render("search"))
		self.assertIn("Publish a page to preview the page layout.", self.render("page"))

	def test_the_empty_preview_tells_the_editor_it_is_ready(self):
		frappe.db.set_value("Shop Web Page", {"published": 1}, "published", 0)

		html = self.render("page", layout=self.starter_layout("page"))

		self.assertIn("Publish a page to preview the page layout.", html)
		self.assertIn("/assets/commera/js/theme_editor_preview.js", html)
		self.assertNotIn("theme_editor_preview.js", self.render("page"))

	def test_the_chosen_product_and_page_render_in_place_of_the_newest(self):
		first_route = self.make_priced_variant("ENTRYONE", default_rate=40)
		second_route = self.make_priced_variant("ENTRYTWO", default_rate=40)
		save_page(title="ZZ Entry One", content="<p>Entry one body</p>", route="zz-entry-one", published=1)
		save_page(title="ZZ Entry Two", content="<p>Entry two body</p>", route="zz-entry-two", published=1)

		for route in (first_route, second_route):
			self.assertIn(f"Display {route}", self.render("product", entry=route))
		self.assertIn("Entry one body", self.render("page", entry="zz-entry-one"))
		self.assertIn("Entry two body", self.render("page", entry="zz-entry-two"))

	def test_an_entry_that_is_not_live_falls_back_to_the_default(self):
		self.make_priced_variant("FALLBACK", default_rate=40)
		save_page(title="ZZ Live Page", content="<p>Live body</p>", route="zz-live-page", published=1)
		save_page(title="ZZ Draft Page", content="<p>Draft body</p>", route="zz-draft-page", published=0)

		self.assertEqual(self.render("product", entry="no-such-product"), self.render("product"))
		draft_preview = self.render("page", entry="zz-draft-page")
		self.assertNotIn("Draft body", draft_preview)
		self.assertEqual(draft_preview, self.render("page"))

	def test_search_and_collection_entries_reach_the_listing(self):
		self.make_priced_variant("SEARCHABLE", default_rate=40)

		self.assertIn("zzunlikelyterm", self.render("search", entry="zzunlikelyterm"))
		self.assertEqual(self.render("products", entry="no-such-collection"), self.render("products"))

	def test_preview_entries_list_live_records_and_resolve_the_current_one(self):
		save_page(title="ZZ Listed Page", content="<p>Listed</p>", route="zz-listed-page", published=1)
		save_page(title="ZZ Hidden Page", content="<p>Hidden</p>", route="zz-hidden-page", published=0)

		listed = get_preview_entries(STARTER_THEME, "page", search="ZZ")
		self.assertEqual([entry["value"] for entry in listed["entries"]], ["zz-listed-page"])
		self.assertEqual(
			get_preview_entries(STARTER_THEME, "page", selected="zz-hidden-page")["current"]["value"],
			get_preview_entries(STARTER_THEME, "page")["current"]["value"],
		)

		collections = get_preview_entries(STARTER_THEME, "products", selected="no-such-collection")
		self.assertEqual(collections["entries"][0], {"value": "", "title": "All products"})
		self.assertEqual(collections["current"], {"value": "", "title": "All products"})

		search = get_preview_entries(STARTER_THEME, "search", search="linen")
		self.assertEqual(search["entries"][0], {"value": "linen", "title": 'Search for "linen"'})

	def test_only_layout_pages_with_records_offer_entries(self):
		self.assertFalse(get_editor(STARTER_THEME, "index")["has_preview_entries"])
		self.assertTrue(get_editor(STARTER_THEME, "page")["has_preview_entries"])

	def test_only_managers_list_preview_entries(self):
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user("Guest")

		self.assertRaises(frappe.PermissionError, get_preview_entries, STARTER_THEME, "page")
