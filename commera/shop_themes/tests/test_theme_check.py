import contextlib
import io
import json
import os
import shutil
import tempfile
from unittest.mock import patch

import click
import frappe
from click.testing import CliRunner
from frappe.tests import IntegrationTestCase, UnitTestCase

from commera.commands import check
from commera.sdk.testing import assert_theme_valid
from commera.shop_themes.section_check import BLOCK_KEYS, SECTION_KEYS, SETTING_KEYS, SETTING_TYPE_KEYS
from commera.shop_themes.tests.theme_fixtures import write_theme_files
from commera.shop_themes.theme_check import check_theme, check_themes_on_disk, print_theme_check_errors
from commera.shop_themes.theme_files import (
	RESERVED_BLOCK_TYPES,
	SETTING_TYPES,
	find_theme_dirs_on_disk,
	theme_file_cache,
)

SHIPPED_THEMES = ("shop_base_theme", "shop_default_theme", "summer_theme")
HERO_HTML = (
	'{% from "components/macros/cards.html" import badge %}\n'
	"{% macro slide(block) %}<p{{ block.editor_attributes }}>{{ block.settings.title }}</p>{% endmacro %}\n"
	"<h2>{{ section.settings.heading }}</h2>\n"
	"{% for block in section.blocks %}{{ render_block(block) }}{% endfor %}\n"
	'{{ render_static_block("badge") }}\n'
)
CLEAN_BASE = {
	"settings.json": {
		"name": "Theme settings",
		"settings": [{"id": "accent", "type": "color", "label": "Accent"}],
	},
	"sections/hero.json": {
		"$schema": "../../section.schema.json",
		"name": "Hero",
		"settings": [
			{"id": "heading", "type": "text", "label": "Heading", "translatable": True},
			{
				"id": "height",
				"type": "select",
				"label": "Height",
				"default": "large",
				"options": ["small", "large"],
			},
			{
				"id": "columns",
				"type": "range",
				"label": "Columns",
				"min": 1,
				"max": 4,
				"step": 1,
				"default": 2,
			},
			{"id": "lookbook", "type": "link", "label": "Lookbook", "doctype": "Item Group"},
		],
		"blocks": {
			"slide": {"name": "Slide", "settings": [{"id": "title", "type": "text", "label": "Title"}]},
			"badge": {"name": "Badge", "static": True},
		},
		"max_blocks": 5,
		"presets": [{"name": "Hero", "blocks": ["slide", {"type": "slide", "settings": {"title": "Two"}}]}],
	},
	"sections/hero.html": HERO_HTML,
	"sections/main.json": {"name": "Main", "static": True, "templates": ["page"]},
	"sections/main.html": "<main>{{ section.settings }}</main>",
	"sections/top_bar.json": {"name": "Top bar", "groups": ["header"]},
	"sections/top_bar.html": "<p>top</p>",
	"layouts/index.json": {
		"sections": [{"id": "hero", "type": "hero", "blocks": [{"id": "slide-1", "type": "slide"}]}]
	},
	"layouts/page.json": {"sections": [{"id": "main", "type": "main"}]},
	"layouts/groups/header.json": {"sections": [{"id": "top_bar", "type": "top_bar"}]},
	"pages/index.html": '{% extends "components/base.html" %}{% block body %}{{ render_layout("index") }}{% endblock %}',
	"styles/theme.css": ".card { margin-inline-start: 1rem; text-align: start; }\n",
}


class ThemeFolderMixin:
	def add_theme_folders(self):
		self.root = tempfile.mkdtemp(prefix="commera_theme_check_")
		self.addCleanup(shutil.rmtree, self.root)
		self.addCleanup(theme_file_cache.clear)
		self.base_dir = os.path.join(self.root, "base")
		self.child_dir = os.path.join(self.root, "child")
		write_theme_files(self.base_dir, CLEAN_BASE)
		os.makedirs(self.child_dir)

	def get_findings(self, files):
		write_theme_files(self.child_dir, files)
		return check_theme([self.child_dir, self.base_dir])

	def assert_finding(self, files, rule, file, line=None):
		findings = self.get_findings(files)
		matching = [finding for finding in findings if finding["rule"] == rule]
		self.assertTrue(matching, f"no {rule} in {findings}")
		self.assertEqual((matching[0]["file"], matching[0]["line"]), (file, line))
		self.assertTrue(matching[0]["message"] and matching[0]["fix"])
		return matching


class UnitTestThemeCheck(ThemeFolderMixin, UnitTestCase):
	def setUp(self):
		self.add_theme_folders()

	def test_clean_theme_and_child_have_no_findings(self):
		self.assertEqual(check_theme([self.base_dir]), [])
		self.assertEqual(self.get_findings({"layouts/index.json": {"sections": []}}), [])

	def test_invalid_json(self):
		self.assert_finding(
			{"sections/banner.json": '{\n "name": "Banner"\n "icon": "star"\n}'},
			"invalid-json",
			"sections/banner.json",
			3,
		)

	def test_schema_invalid(self):
		banner = {
			"name": "Banner",
			"colour": "red",
			"max_blocks": 80,
			"groups": ["sidebar"],
			"settings": [
				{"id": "Size", "type": "number", "label": "Size"},
				{"id": "width", "type": "range", "label": "Width"},
				{"id": "kind", "type": "text", "label": "Kind", "options": ["a"]},
				{"id": "count", "type": "check", "label": "Count", "default": "yes"},
			],
			"presets": [{"blocks": ["missing"]}],
		}
		findings = self.get_findings({"sections/banner.json": banner, "sections/banner.html": "<p></p>"})
		messages = [finding["message"] for finding in findings if finding["rule"] == "schema-invalid"]
		for expected in (
			'unknown key "colour"',
			"max_blocks must be a whole number",
			"groups must be null",
			'setting "Size": id must be snake_case',
			'setting "Size": type must be one of',
			'setting "width": range needs numbers min and max',
			'setting "kind": unknown key "options"',
			'setting "count": default is not a valid check value',
			'preset 1 uses unknown block type "missing"',
		):
			self.assertTrue(any(expected in message for message in messages), f"{expected} not in {messages}")

	def test_duplicate_setting_id(self):
		settings = [{"id": "accent", "type": "color"}, {"id": "accent", "type": "text"}]
		self.assert_finding(
			{"settings.json": {"settings": settings}}, "duplicate-setting-id", "settings.json", 1
		)

	def test_select_default_invalid(self):
		schema = {
			"name": "Banner",
			"settings": [
				{"id": "label", "type": "text"},
				{
					"id": "height",
					"type": "select",
					"default": "xl",
					"options": [{"value": "small", "label": "S"}],
				},
			],
		}
		matching = self.assert_finding(
			{"sections/banner.json": json.dumps(schema, indent=1), "sections/banner.html": "<p></p>"},
			"select-default-invalid",
			"sections/banner.json",
			9,
		)
		self.assertIn('default "xl" is not one of small', matching[0]["message"])

	def test_block_macro_missing(self):
		schema = {"name": "Quotes", "blocks": {"quote": {"name": "Quote"}, "badge": {"name": "Badge"}}}
		html = (
			'{% from "components/macros/cards.html" import card, badge as badge with context %}'
			"{% for block in section.blocks %}{{ render_block(block) }}{% endfor %}"
		)
		matching = self.assert_finding(
			{"sections/quotes.json": schema, "sections/quotes.html": html},
			"block-macro-missing",
			"sections/quotes.json",
		)
		self.assertEqual(len(matching), 1)
		self.assertIn("{% macro quote(block) %}", matching[0]["message"])

	def test_block_macro_missing_in_an_inherited_template(self):
		schema = {
			**CLEAN_BASE["sections/hero.json"],
			"blocks": {"slide": {"name": "Slide"}, "quote": {"name": "Quote"}},
		}
		self.assert_finding({"sections/hero.json": schema}, "block-macro-missing", "sections/hero.json")

	def test_macro_without_block(self):
		html = "<p></p>\n{% macro price_tag(value) %}{{ value }}{% endmacro %}"
		self.assert_finding(
			{"sections/banner.json": {"name": "Banner"}, "sections/banner.html": html},
			"macro-without-block",
			"sections/banner.html",
			2,
		)

	def test_block_editor_attributes_missing(self):
		schema = {"name": "Quotes", "blocks": {"quote": {"name": "Quote"}, "author": {"name": "Author"}}}
		html = (
			"{% macro quote(item) %}<q{{ item.editor_attributes }}>{{ item.settings.text }}</q>{% endmacro %}\n"
			"{% macro author(block) %}\n<cite>{{ block.settings.name }}</cite>\n{% endmacro %}\n"
			"{% for block in section.blocks %}{{ render_block(block) }}{% endfor %}"
		)
		matching = self.assert_finding(
			{"sections/quotes.json": schema, "sections/quotes.html": html},
			"block-editor-attributes-missing",
			"sections/quotes.html",
			2,
		)
		self.assertEqual(len(matching), 1)
		self.assertIn('"author"', matching[0]["message"])

	def test_section_template_missing(self):
		self.assert_finding(
			{"sections/banner.json": {"name": "Banner"}}, "section-template-missing", "sections/banner.json"
		)

	def test_reserved_block_type(self):
		schema = {"name": "Picks", "blocks": {"product": {"name": "Product"}}}
		html = "{% macro product(block) %}{% endmacro %}{% for block in section.blocks %}{{ render_block(block) }}{% endfor %}"
		self.assert_finding(
			{"sections/picks.json": schema, "sections/picks.html": html},
			"reserved-block-type",
			"sections/picks.json",
			1,
		)

	def test_layout_invalid(self):
		layout = {"sections": [{"id": "bad id!", "type": "hero"}, {"id": "top_bar", "type": "top_bar"}]}
		matching = self.assert_finding({"layouts/index.json": layout}, "layout-invalid", "layouts/index.json")
		self.assertEqual(len(matching), 2)

	def test_layout_unknown_section(self):
		layout = {"sections": [{"id": "promo", "type": "promo_strip"}]}
		self.assert_finding({"layouts/index.json": layout}, "layout-unknown-section", "layouts/index.json")

	def test_layout_unknown_block(self):
		layout = {"sections": [{"id": "hero", "type": "hero", "blocks": [{"id": "b1", "type": "quote"}]}]}
		self.assert_finding({"layouts/index.json": layout}, "layout-unknown-block", "layouts/index.json")

	def test_layout_link_values_are_not_looked_up(self):
		layout = {"sections": [{"id": "hero", "type": "hero", "settings": {"lookbook": "No Such Group"}}]}
		self.assertEqual(self.get_findings({"layouts/index.json": layout}), [])

	def test_static_section_missing(self):
		self.assert_finding(
			{"layouts/page.json": {"sections": []}}, "static-section-missing", "layouts/page.json"
		)

	def test_blocks_not_looped(self):
		html = "{% macro quote(block) %}{% endmacro %}{{ render_block(section.blocks[0]) }}"
		schema = {"name": "Quotes", "blocks": {"quote": {"name": "Quote"}}}
		self.assert_finding(
			{"sections/quotes.json": schema, "sections/quotes.html": html},
			"blocks-not-looped",
			"sections/quotes.html",
		)

	def test_physical_css_property(self):
		css = ".a { color: red; }\n.b { margin-left: 4px; border-right-width: 1px; }\n.c { left: 0; text-align: right; }\n"
		findings = self.get_findings({"styles/theme.css": css})
		self.assertEqual(
			[(finding["line"], finding["message"].split(" breaks")[0]) for finding in findings],
			[(2, "margin-left"), (2, "border-right-width"), (3, "left"), (3, "text-align: right")],
		)
		self.assertIn("margin-inline-start", findings[0]["message"])
		self.assertEqual({finding["severity"] for finding in findings}, {"warning"})

	def test_translatable_printed_safe(self):
		html = HERO_HTML + "<p>{{ section.settings.heading | safe }}</p>\n"
		self.assert_finding(
			{"sections/hero.html": html}, "translatable-printed-safe", "sections/hero.html", 6
		)

	def test_template_without_layout(self):
		page = '{% block body %}\n{{ render_layout("product") }}\n{% endblock %}'
		self.assert_finding({"pages/product.html": page}, "template-without-layout", "pages/product.html", 2)

	def test_section_schema_json_matches_the_engine(self):
		with open(frappe.get_app_path("commera", "themes", "section.schema.json")) as schema_file:
			schema = json.load(schema_file)
		setting = schema["$defs"]["setting"]
		self.assertEqual(set(setting["properties"]["type"]["enum"]), SETTING_TYPES)
		self.assertEqual(set(schema["properties"]), SECTION_KEYS)
		self.assertEqual(set(schema["$defs"]["block"]["properties"]), BLOCK_KEYS)
		self.assertEqual(set(setting["properties"]), SETTING_KEYS.union(*SETTING_TYPE_KEYS.values()))
		self.assertEqual(
			set(schema["properties"]["blocks"]["propertyNames"]["not"]["enum"]), RESERVED_BLOCK_TYPES
		)


class UnitTestThemesOnDisk(UnitTestCase):
	def setUp(self):
		self.apps_path = tempfile.mkdtemp(prefix="commera_theme_apps_")
		self.addCleanup(shutil.rmtree, self.apps_path)
		self.addCleanup(theme_file_cache.clear)

	def add_theme(self, app, name, parent=None, files=None):
		package_path = os.path.join(self.apps_path, app, app)
		slug = frappe.scrub(name)
		record = {"doctype": "Shop Theme", "name": name, "theme_name": name, "parent_theme": parent}
		record_path = f"theme_records/shop_theme/{slug}/{slug}.json"
		write_theme_files(package_path, {"modules.txt": "Theme Records\n", record_path: record})
		if files is not None:
			write_theme_files(os.path.join(package_path, "themes", slug), files)
		return os.path.join(package_path, "themes", slug)

	def test_chain_crosses_apps_and_skips_themes_without_a_folder(self):
		base_dir = self.add_theme("base_app", "Base Theme", files={"settings.json": {"settings": []}})
		self.add_theme("base_app", "Middle Theme", parent="Base Theme")
		child_dir = self.add_theme(
			"child_app", "Child Theme", parent="Middle Theme", files={"sections/.gitkeep": ""}
		)
		self.assertEqual(find_theme_dirs_on_disk("child_theme", self.apps_path), [child_dir, base_dir])
		self.assertEqual(find_theme_dirs_on_disk("missing_theme", self.apps_path), [])

	def test_chain_stops_on_a_cycle(self):
		one_dir = self.add_theme("loop_app", "One", parent="Two", files={"sections/.gitkeep": ""})
		two_dir = self.add_theme("loop_app", "Two", parent="One", files={"sections/.gitkeep": ""})
		self.assertEqual(find_theme_dirs_on_disk("one", self.apps_path), [one_dir, two_dir])

	def test_check_every_theme_tags_findings_with_the_theme(self):
		self.add_theme("base_app", "Base Theme", files={"settings.json": "{"})
		self.add_theme("base_app", "No Folder Theme")
		findings = check_themes_on_disk(apps_path=self.apps_path)
		self.assertEqual(
			[(finding["theme"], finding["rule"]) for finding in findings], [("base_theme", "invalid-json")]
		)
		with self.assertRaises(click.UsageError):
			check_themes_on_disk("no_folder_theme", self.apps_path)


class UnitTestShippedThemes(UnitTestCase):
	def test_shipped_themes_have_no_errors(self):
		for slug in SHIPPED_THEMES:
			with self.subTest(slug):
				assert_theme_valid(slug)
		assert_theme_valid("Summer Theme")

	def test_assert_theme_valid_lists_the_errors(self):
		with self.assertRaisesRegex(AssertionError, "No theme folder"):
			assert_theme_valid("no_such_theme")

		root = tempfile.mkdtemp(prefix="commera_theme_assert_")
		self.addCleanup(shutil.rmtree, root)
		broken_dir = os.path.join(root, "broken_theme")
		write_theme_files(broken_dir, {"sections/broken.json": {"name": "Broken"}})
		with patch("commera.sdk.testing.find_theme_dirs_on_disk", return_value=[broken_dir]):
			with self.assertRaisesRegex(
				AssertionError, "sections/broken.json .* has no sections/broken.html"
			):
				assert_theme_valid("broken_theme")

	def test_check_command_exit_codes(self):
		result = CliRunner().invoke(check, ["--theme", "summer_theme", "--json"])
		self.assertEqual((result.exit_code, json.loads(result.output)), (0, []))

		result = CliRunner().invoke(check, ["--theme", "no_such_theme"])
		self.assertEqual(result.exit_code, 2)

		error = {
			"rule": "invalid-json",
			"severity": "error",
			"file": "a.json",
			"line": 1,
			"message": "bad",
			"fix": "fix",
		}
		with patch("commera.shop_themes.theme_check.check_themes_on_disk", return_value=[error]):
			result = CliRunner().invoke(check, [])
		self.assertEqual(result.exit_code, 1)
		self.assertEqual(result.output.splitlines()[-1], "1 error, 0 warnings")


class IntegrationTestThemeCheckAfterMigrate(IntegrationTestCase):
	def test_installed_themes_print_no_errors(self):
		self.assertTrue(frappe.get_all("Shop Theme", limit=1))
		failure_filters = {"method": "Theme check after migrate failed"}
		failures_before = len(frappe.get_all("Error Log", filters=failure_filters, pluck="name"))
		output = io.StringIO()
		with contextlib.redirect_stdout(output):
			print_theme_check_errors()
		self.assertEqual(output.getvalue(), "")
		self.assertEqual(
			len(frappe.get_all("Error Log", filters=failure_filters, pluck="name")), failures_before
		)
