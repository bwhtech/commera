# Copyright (c) 2026, BWH Tech and contributors

import os
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime
from frappe.utils.jinja import get_jenv
from markupsafe import Markup, escape

from commera.shop_themes.layouts import layout_override
from commera.shop_themes.section_data import block_products_cache, get_block_products
from commera.shop_themes.section_render import (
	EDITOR_LOCAL_KEY,
	format_theme_settings_css,
	get_theme_settings,
	resolve_section,
	resolve_settings,
)
from commera.shop_themes.tests.theme_fixtures import ThemeFixtureMixin
from commera.shop_themes.theme_files import (
	find_theme_file,
	get_default_layout,
	get_section_schema,
	get_section_schemas,
	get_settings_schema,
	is_valid_setting_value,
	list_layout_templates,
	load_theme_module,
	read_theme_json,
	theme_file_cache,
)
from commera.shop_themes.theme_resolver import build_base_context, get_theme_environment, load_page_controller
from commera.utils import get_product_list


class IntegrationTestThemeFiles(ThemeFixtureMixin, IntegrationTestCase):
	def setUp(self):
		self.add_fixture_theme()

	def test_sections_resolve_child_first_and_inherit_the_rest(self):
		schemas = get_section_schemas(self.theme_dirs)
		self.assertIn("hero", schemas)
		self.assertIn("child_only", schemas)
		self.assertEqual(schemas["banner"]["name"], "Banner")
		self.assertEqual(
			find_theme_file(self.theme_dirs, "sections/banner.html"),
			os.path.join(self.child_dir, "sections", "banner.html"),
		)
		self.assertEqual(
			find_theme_file(self.theme_dirs, "sections/banner.json"),
			os.path.join(self.parent_dir, "sections", "banner.json"),
		)

	def test_a_child_schema_overrides_the_parents_for_one_type(self):
		self.write_fixture_file(self.child_dir, "sections/banner.json", {"name": "Child banner"})
		self.assertEqual(get_section_schema(self.theme_dirs, "banner")["name"], "Child banner")
		self.assertEqual(get_section_schema(self.theme_dirs, "hero")["name"], "Hero")

	def test_layout_files_resolve_child_first(self):
		self.assertEqual(
			get_default_layout(self.theme_dirs, "collection")["sections"][0]["id"], "child_banner"
		)
		self.assertEqual(get_default_layout(self.theme_dirs, "index")["sections"][0]["id"], "hero")
		self.assertEqual(get_default_layout(self.theme_dirs, "product"), {"sections": []})
		self.assertEqual(get_default_layout(self.theme_dirs, "settings"), {"settings": {}})

	def test_layout_templates_list_pages_and_groups(self):
		self.assertEqual(
			list_layout_templates(self.theme_dirs), ["collection", "index", "page", "group:header"]
		)

	def test_the_child_settings_file_replaces_the_parents_whole(self):
		settings = get_settings_schema(self.theme_dirs)
		self.assertEqual([setting["id"] for setting in settings], ["radius", "page_width"])
		self.assertEqual(settings[0]["max"], 40)

		os.remove(os.path.join(self.child_dir, "settings.json"))
		self.assertEqual(
			[setting["id"] for setting in get_settings_schema(self.theme_dirs)],
			["accent", "radius", "tagline"],
		)

	def test_production_caches_theme_json_until_the_worker_restarts(self):
		self.addCleanup(theme_file_cache.clear)
		self.addCleanup(setattr, frappe.conf, "developer_mode", frappe.conf.developer_mode)
		frappe.conf.developer_mode = 0
		self.assertEqual(read_theme_json(self.theme_dirs, "sections/banner.json")["name"], "Banner")

		self.write_fixture_file(self.parent_dir, "sections/banner.json", {"name": "Edited"})
		self.assertEqual(read_theme_json(self.theme_dirs, "sections/banner.json")["name"], "Banner")

		frappe.conf.developer_mode = 1
		self.assertEqual(read_theme_json(self.theme_dirs, "sections/banner.json")["name"], "Edited")

	def test_a_default_layout_is_a_copy_of_the_cached_file(self):
		self.addCleanup(theme_file_cache.clear)
		self.addCleanup(setattr, frappe.conf, "developer_mode", frappe.conf.developer_mode)
		frappe.conf.developer_mode = 0
		get_default_layout(self.theme_dirs, "index")["sections"].clear()
		self.assertTrue(get_default_layout(self.theme_dirs, "index")["sections"])

	def test_an_unparsable_schema_is_skipped_and_logged(self):
		started_at = now_datetime()
		self.write_fixture_file(self.child_dir, "sections/broken.json", "{not json")
		self.assertNotIn("broken", get_section_schemas(self.theme_dirs))
		self.assertTrue(
			frappe.get_all(
				"Error Log",
				filters={
					"method": "Theme file is not valid JSON",
					"error": ["like", "%sections/broken.json%"],
					"creation": [">=", started_at],
				},
				limit=1,
			)
		)

	def test_section_controllers_load_under_their_own_namespace(self):
		module = load_theme_module(self.theme_dirs, "sections/with_data.py", "theme_sections")
		self.assertEqual(
			module.__name__, "commera.shop_themes.theme_sections.fixture_parent.sections_with_data"
		)
		self.assertIs(load_theme_module(self.theme_dirs, "sections/with_data.py", "theme_sections"), module)

	def test_page_controllers_still_load_under_theme_pages(self):
		self.write_fixture_file(self.parent_dir, "pages/about.py", "def get_context(context):\n\tpass\n")
		module = load_page_controller(self.theme_dirs, "pages/about.html")
		self.assertEqual(module.__name__, "commera.shop_themes.theme_pages.fixture_parent.pages_about")


class IntegrationTestSectionResolution(ThemeFixtureMixin, IntegrationTestCase):
	def setUp(self):
		self.add_fixture_theme()
		self.hero_schema = get_section_schema(self.theme_dirs, "hero")

	def resolve_hero(self, settings=None, blocks=None, language="en"):
		stored = {"id": "hero", "type": "hero", "settings": settings or {}, "blocks": blocks or []}
		return resolve_section(self.hero_schema, stored, language)

	def test_every_setting_takes_its_default_when_nothing_is_stored(self):
		settings = self.resolve_hero().settings
		self.assertEqual(settings.heading, "Welcome")
		self.assertEqual(settings.height, "large")
		self.assertEqual(settings.count, 4)
		self.assertIs(settings.autoplay, True)
		self.assertEqual((settings.link, settings.accent, settings.collection), ("", "", ""))

	def test_unknown_setting_ids_are_ignored(self):
		self.assertNotIn("retired", self.resolve_hero({"retired": "x"}).settings)

	def test_a_stored_value_of_the_wrong_type_falls_back_to_the_default(self):
		settings = self.resolve_hero(
			{"height": "huge", "count": 11, "autoplay": "yes", "accent": "red", "link": {"en": "/x"}}
		).settings
		self.assertEqual(settings.height, "large")
		self.assertEqual(settings.count, 4)
		self.assertIs(settings.autoplay, True)
		self.assertEqual(settings.accent, "")
		self.assertEqual(settings.link, "")

	def test_valid_stored_values_win(self):
		settings = self.resolve_hero(
			{"height": "small", "count": 10, "autoplay": False, "accent": "#0a0"}
		).settings
		self.assertEqual(
			(settings.height, settings.count, settings.autoplay, settings.accent),
			("small", 10, False, "#0a0"),
		)

	def test_translatable_values_resolve_to_the_language_with_english_fallback(self):
		heading = {"en": "Long days", "ar": "أيام طويلة"}
		self.assertEqual(self.resolve_hero({"heading": heading}, language="en").settings.heading, "Long days")
		self.assertEqual(
			self.resolve_hero({"heading": heading}, language="ar").settings.heading, "أيام طويلة"
		)
		self.assertEqual(
			self.resolve_hero({"heading": {"en": "Only English"}}, language="ar").settings.heading,
			"Only English",
		)
		self.assertEqual(self.resolve_hero({"heading": "Plain"}, language="ar").settings.heading, "Plain")
		self.assertEqual(self.resolve_hero(language="ar").settings.heading, "أهلا")

	def test_text_is_escaped_once(self):
		heading = self.resolve_hero({"heading": '<b class="x">Tom & Jerry</b>'}).settings.heading
		self.assertIsInstance(heading, Markup)
		self.assertEqual(heading, "&lt;b class=&#34;x&#34;&gt;Tom &amp; Jerry&lt;/b&gt;")
		self.assertEqual(escape(heading), heading)

	def test_a_url_outside_the_allowed_schemes_resolves_to_empty(self):
		for link in (
			"javascript:alert(1)",
			"  JavaScript:alert(1)",
			"java\tscript:alert(1)",
			"data:text/html,<script>alert(1)</script>",
			"vbscript:msgbox(1)",
		):
			self.assertEqual(self.resolve_hero({"link": link}).settings.link, "", link)
		for link in (
			"/en/products",
			"products?page=2",
			"#top",
			"https://example.com",
			"mailto:a@b.co",
			"tel:+1",
		):
			self.assertEqual(self.resolve_hero({"link": link}).settings.link, link)

	def test_an_image_must_be_a_file_or_web_address_that_cannot_break_css(self):
		image_setting = {"id": "image", "type": "image"}
		for image in (
			"",
			"/files/a b.png",
			"/private/files/a.png",
			"/assets/x/a.webp",
			"https://cdn.example/a.png",
		):
			self.assertTrue(is_valid_setting_value(image_setting, image), image)
		for image in (
			"x');position:fixed;inset:0;background:url('https://attacker/overlay.png",
			'/files/a".png',
			"/files/a(1).png",
			"/files/a\\b.png",
			"data:image/svg+xml,<svg/>",
			"javascript:alert(1)",
			"files/a.png",
		):
			self.assertFalse(is_valid_setting_value(image_setting, image), image)

	def test_only_renderable_blocks_are_kept_and_numbered(self):
		section = self.resolve_hero(
			blocks=[
				{"id": "a", "type": "slide", "settings": {"title": "A"}},
				{"id": "b", "type": "slide", "disabled": True},
				{"id": "c", "type": "retired_block"},
				{"id": "d", "type": "app:some_app/size_chart"},
				{"id": "e", "type": "slide", "settings": {"title": "E"}},
				"not a block",
			]
		)
		self.assertEqual([(block.id, block.index) for block in section.blocks], [("a", 1), ("e", 2)])

	def test_a_static_block_comes_from_the_layout_or_its_defaults(self):
		self.assertEqual(self.resolve_hero().static_blocks.badge.settings.label, "New")
		stored = self.resolve_hero(blocks=[{"id": "badge-1", "type": "badge", "settings": {"label": "Sale"}}])
		self.assertEqual(stored.static_blocks.badge.id, "badge-1")
		self.assertEqual(stored.blocks, [])
		hidden = self.resolve_hero(blocks=[{"id": "badge-1", "type": "badge", "disabled": True}])
		self.assertIsNone(hidden.static_blocks.badge)

	def test_theme_settings_resolve_against_the_merged_schema(self):
		settings = resolve_settings(get_settings_schema(self.theme_dirs), {"radius": 30}, "en")
		self.assertEqual(settings, {"radius": 30, "page_width": 1280})


class IntegrationTestRenderLayout(ThemeFixtureMixin, IntegrationTestCase):
	def setUp(self):
		self.add_fixture_theme()
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
		self.addCleanup(setattr, frappe.conf, "developer_mode", frappe.conf.developer_mode)
		frappe.local.lang = "en"

	def render(self, template="index", **context):
		theme_env = get_theme_environment(get_jenv(), self.theme_dirs)
		return theme_env.from_string(f'{{{{ render_layout("{template}") }}}}').render(context)

	def render_sections(self, *sections, template="index"):
		with layout_override(template, {"sections": list(sections)}):
			return self.render(template)

	def count_error_logs(self, title, started_at):
		return len(frappe.get_all("Error Log", filters={"method": title, "creation": [">=", started_at]}))

	def test_sections_render_in_order_and_skip_hidden_and_unknown_ones(self):
		html = self.render(page_marker="home")
		self.assertEqual(
			html,
			'<section id="section-hero" data-section-type="hero"><div class="hero-small">Welcome'
			'<p class="slide">1:One</p><p class="slide">2:Three</p><span class="badge">New</span></div></section>'
			'<section id="section-banner" data-section-type="banner">'
			'<div class="banner-child">Parent banner</div></section>'
			'<section id="section-with_data" data-section-type="with_data">'
			"<p>Data!|hero,banner,gated,with_data|home</p></section>",
		)

	def test_a_section_that_renders_nothing_leaves_no_markup(self):
		self.assertEqual(self.render_sections({"id": "gated", "type": "gated"}), "")
		self.assertIn(
			"<p>shown</p>", self.render_sections({"id": "gated", "type": "gated", "settings": {"show": True}})
		)

	def test_a_stored_static_block_renders_in_its_fixed_place(self):
		html = self.render_sections(
			{
				"id": "hero",
				"type": "hero",
				"blocks": [
					{"id": "badge-1", "type": "badge", "settings": {"label": "Sale"}},
					{"id": "slide-1", "type": "slide", "settings": {"title": "First"}},
				],
			}
		)
		self.assertIn('<p class="slide">1:First</p><span class="badge">Sale</span>', html)

	def test_header_and_footer_groups_render_around_the_page(self):
		with layout_override("group:header", {"sections": [{"id": "bar", "type": "header_bar"}]}):
			html = self.render_sections({"id": "banner", "type": "banner"})
		self.assertTrue(html.startswith('<section id="section-bar" data-section-type="header_bar">'))

	def test_the_editor_marks_sections_and_blocks_on_their_own_root(self):
		hero = {"id": "hero", "type": "hero", "blocks": [{"id": "s1", "type": "slide"}]}
		self.addCleanup(setattr, frappe.local, EDITOR_LOCAL_KEY, None)
		setattr(frappe.local, EDITOR_LOCAL_KEY, True)
		html = self.render_sections(hero)
		self.assertIn('data-section-id="hero"', html)
		self.assertIn('<p class="slide" data-block-id="s1">', html)
		self.assertIn('<span class="badge" data-block-id="badge">', html)
		self.assertNotIn("display: contents", html)

		setattr(frappe.local, EDITOR_LOCAL_KEY, None)
		html = self.render_sections(hero)
		self.assertNotIn("data-section-id", html)
		self.assertNotIn("data-block-id", html)
		self.assertIn('<p class="slide">', html)

	def test_the_editor_keeps_a_selectable_wrapper_for_an_empty_section(self):
		self.addCleanup(setattr, frappe.local, EDITOR_LOCAL_KEY, None)
		setattr(frappe.local, EDITOR_LOCAL_KEY, True)
		html = self.render_sections({"id": "gated", "type": "gated"})
		self.assertTrue(
			html.startswith(
				'<section id="section-gated" data-section-type="gated" data-section-id="gated" data-section-empty="1"><p>'
			)
		)
		self.assertIn("gated", html)

	def test_arabic_renders_arabic_values(self):
		frappe.local.lang = "ar"
		self.assertIn("أهلا", self.render_sections({"id": "hero", "type": "hero"}))

	def test_theme_settings_reach_templates_and_css(self):
		self.write_fixture_file(self.child_dir, "sections/banner.html", "{{ theme_settings.radius }}")
		self.assertIn(">12</section>", self.render_sections({"id": "banner", "type": "banner"}))
		self.assertEqual(
			format_theme_settings_css({}),
			"<style>:root{--theme-radius: 12px; --theme-page_width: 1280px;}</style>",
		)
		page_settings = frappe._dict(radius=4, page_width=960)
		self.assertEqual(
			format_theme_settings_css({"theme_settings": page_settings}),
			"<style>:root{--theme-radius: 4px; --theme-page_width: 960px;}</style>",
		)
		self.assertEqual(build_base_context(None).theme_settings, get_theme_settings(self.theme_context))

	def test_a_theme_without_settings_emits_no_css(self):
		os.remove(os.path.join(self.parent_dir, "settings.json"))
		os.remove(os.path.join(self.child_dir, "settings.json"))
		self.assertEqual(format_theme_settings_css({}), "")
		self.assertEqual(get_theme_settings(self.theme_context), {})

	def test_a_failing_controller_or_template_skips_only_that_section_and_logs_once(self):
		frappe.conf.developer_mode = 0
		started_at = now_datetime()
		sections = (
			{"id": "first", "type": "banner"},
			{"id": "bad_controller", "type": "broken_controller"},
			{"id": "bad_template", "type": "broken_template"},
			{"id": "last", "type": "child_only"},
		)
		for _attempt in range(2):
			html = self.render_sections(*sections)
			self.assertIn('id="section-first"', html)
			self.assertIn('id="section-last"', html)
			self.assertNotIn("never", html)
			self.assertNotIn("bad_", html)

		self.assertEqual(self.count_error_logs("Theme section broken_controller failed", started_at), 1)
		self.assertEqual(self.count_error_logs("Theme section broken_template failed", started_at), 1)

	def test_developer_mode_shows_a_placeholder_naming_the_failed_section(self):
		frappe.conf.developer_mode = 1
		html = self.render_sections({"id": "bad", "type": "broken_controller"})
		self.assertIn('data-section-error="1"', html)
		self.assertIn("Section broken_controller could not be rendered: controller boom", html)

	def test_a_block_without_a_macro_renders_nothing_and_is_logged(self):
		started_at = now_datetime()
		html = self.render_sections(
			{"id": "quotes", "type": "missing_macro", "blocks": [{"id": "q1", "type": "quote"}]}
		)
		self.assertIn("<div></div>", html)
		self.assertEqual(self.count_error_logs("Theme block quote has no macro", started_at), 1)

	def test_app_blocks_render_nothing_until_app_blocks_ship(self):
		html = self.render_sections(
			{
				"id": "apps",
				"type": "app_ready",
				"blocks": [
					{"id": "n1", "type": "note", "settings": {"text": "kept"}},
					{"id": "a1", "type": "app:some_app/size_chart"},
				],
			}
		)
		self.assertNotIn("size_chart", html)
		self.assertIn("<div><i>kept</i></div>", html)


class IntegrationTestBlockProducts(IntegrationTestCase):
	def pick(self, block_id, product):
		return frappe._dict(id=block_id, type="pick", settings=frappe._dict(product=escape(product)))

	def test_cards_follow_block_order_and_unknown_products_drop_out(self):
		names = [card["name"] for card in get_product_list(page_length=2)]
		if len(names) < 2:
			self.skipTest("needs two published products")

		blocks = [self.pick("b1", names[1]), self.pick("b2", "No Such Variant"), self.pick("b3", names[0])]
		cards, cards_by_block = get_block_products(blocks)
		self.assertEqual([card["name"] for card in cards], [names[1], names[0]])
		self.assertEqual(sorted(cards_by_block), ["b1", "b3"])

	def test_no_picks_means_no_products(self):
		self.assertEqual(get_block_products([self.pick("b1", "")]), ([], {}))
		self.assertEqual(get_block_products([]), ([], {}))

	def test_one_render_fetches_each_product_once(self):
		names = [card["name"] for card in get_product_list(page_length=2)]
		if len(names) < 2:
			self.skipTest("needs two published products")

		with (
			patch("commera.shop_themes.section_data.get_product_list", wraps=get_product_list) as fetch,
			block_products_cache(),
		):
			get_block_products([self.pick("b1", names[0]), self.pick("b2", "No Such Variant")])
			cards, _cards_by_block = get_block_products(
				[self.pick("c1", names[0]), self.pick("c2", "No Such Variant"), self.pick("c3", names[1])]
			)
		self.assertEqual([card["name"] for card in cards], names)
		self.assertEqual(
			[call.kwargs["product_list"] for call in fetch.call_args_list],
			[[names[0], "No Such Variant"], [names[1]]],
		)
