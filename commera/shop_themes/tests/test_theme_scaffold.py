import json
import os
import shutil
import tempfile
from pathlib import Path

import click
import frappe
from frappe.tests import UnitTestCase

from commera.shop_themes.section_scaffold import create_block, create_section
from commera.shop_themes.tests.theme_fixtures import write_theme_files
from commera.shop_themes.theme_check import check_theme
from commera.shop_themes.theme_files import find_theme_dirs_on_disk, theme_file_cache
from commera.shop_themes.theme_scaffold import create_theme
from commera.tests.test_scaffold import APP, make_app

STARTER_LAYOUT = {"sections": [{"id": "hero", "type": "hero"}]}
STARTER_SETTINGS = {
	"name": "Theme settings",
	"settings": [{"id": "accent", "type": "color", "label": "Accent", "default": ""}],
}


class StarterThemeMixin:
	def add_starter_theme(self):
		self.apps_path = tempfile.mkdtemp(prefix="commera_theme_new_")
		self.addCleanup(shutil.rmtree, self.apps_path)
		self.addCleanup(theme_file_cache.clear)
		make_app(Path(self.apps_path))
		self.starter_dir = os.path.join(self.apps_path, "starter_app", "starter_app", "themes", "starter")
		record = {"doctype": "Shop Theme", "name": "Starter", "theme_name": "Starter"}
		write_theme_files(
			os.path.join(self.apps_path, "starter_app", "starter_app"),
			{"modules.txt": "Starter\n", "starter/shop_theme/starter/starter.json": record},
		)
		write_theme_files(
			self.starter_dir,
			{
				"sections/hero.json": {"name": "Hero"},
				"sections/hero.html": "<p>hero</p>",
				"layouts/index.json": STARTER_LAYOUT,
				"settings.json": STARTER_SETTINGS,
			},
		)


class UnitTestThemeScaffold(StarterThemeMixin, UnitTestCase):
	def setUp(self):
		self.add_starter_theme()

	def read_json(self, relative_path):
		with open(os.path.join(self.apps_path, APP, relative_path)) as json_file:
			return json.load(json_file)

	def test_new_theme_inherits_the_parent_and_passes_check(self):
		result = create_theme(self.apps_path, APP, "atelier", parent="starter")

		module_folder = frappe.scrub(self.get_first_module())
		self.assertEqual(result["theme"], "Atelier")
		self.assertEqual(
			result["created"],
			[
				f"{APP}/themes/atelier/settings.json",
				f"{APP}/themes/atelier/sections/.gitkeep",
				f"{APP}/themes/atelier/layouts/index.json",
				f"{APP}/themes/atelier/layouts/page.json",
				f"{APP}/themes/atelier/layouts/groups/header.json",
				f"{APP}/themes/atelier/layouts/groups/footer.json",
				f"{APP}/{module_folder}/shop_theme/__init__.py",
				f"{APP}/{module_folder}/shop_theme/atelier/__init__.py",
				f"{APP}/{module_folder}/shop_theme/atelier/atelier.json",
			],
		)
		self.assertEqual(self.read_json(f"{APP}/themes/atelier/layouts/index.json"), STARTER_LAYOUT)
		self.assertEqual(self.read_json(f"{APP}/themes/atelier/layouts/page.json"), {"sections": []})
		self.assertEqual(self.read_json(f"{APP}/themes/atelier/settings.json"), STARTER_SETTINGS)

		record = self.read_json(f"{APP}/{module_folder}/shop_theme/atelier/atelier.json")
		self.assertEqual(
			{
				key: record[key]
				for key in ("doctype", "name", "theme_name", "is_standard", "module", "parent_theme")
			},
			{
				"doctype": "Shop Theme",
				"name": "Atelier",
				"theme_name": "Atelier",
				"is_standard": 1,
				"module": self.get_first_module(),
				"parent_theme": "Starter",
			},
		)

		theme_dirs = find_theme_dirs_on_disk("atelier", self.apps_path)
		self.assertEqual(
			theme_dirs, [os.path.join(self.apps_path, APP, APP, "themes", "atelier"), self.starter_dir]
		)
		self.assertEqual(check_theme(theme_dirs), [])

	def test_name_and_module_can_be_chosen(self):
		result = create_theme(
			self.apps_path, APP, "summer_sale", "starter", "Summer Sale", self.get_first_module()
		)
		self.assertEqual(result["theme"], "Summer Sale")

	def test_refuses_bad_arguments(self):
		create_theme(self.apps_path, APP, "atelier", parent="starter")
		os.makedirs(os.path.join(self.apps_path, "starter_app", "starter_app", "themes", "orphan"))
		cases = {
			"unknown app": dict(app="no_such_app", slug="fresh"),
			"slug not snake_case": dict(slug="Fresh-Theme"),
			"slug already a theme": dict(slug="atelier"),
			"slug already a folder": dict(slug="orphan"),
			"unknown parent": dict(slug="fresh", parent="no_such_theme"),
			"name that does not scrub to the slug": dict(slug="fresh", theme_name="Other Name"),
			"unknown module": dict(slug="fresh", module="No Such Module"),
		}
		for case, arguments in cases.items():
			with self.subTest(case), self.assertRaises(click.UsageError):
				create_theme(self.apps_path, **{"app": APP, "parent": "starter", **arguments})
		self.assertFalse(os.path.exists(os.path.join(self.apps_path, APP, APP, "themes", "fresh")))

	def get_first_module(self):
		with open(os.path.join(self.apps_path, APP, APP, "modules.txt")) as modules_file:
			return modules_file.readline().strip()


class UnitTestSectionScaffold(StarterThemeMixin, UnitTestCase):
	def setUp(self):
		self.add_starter_theme()
		create_theme(self.apps_path, APP, "atelier", parent="starter")
		self.theme_dir = os.path.join(self.apps_path, APP, APP, "themes", "atelier")

	def assert_theme_clean(self):
		theme_file_cache.clear()
		self.assertEqual(check_theme(find_theme_dirs_on_disk("atelier", self.apps_path)), [])

	def read_theme_file(self, relative_path):
		with open(os.path.join(self.theme_dir, relative_path)) as theme_file:
			return theme_file.read()

	def test_section_with_blocks_then_more_blocks_stays_clean(self):
		result = create_section("atelier", "testimonials", ["quote"], apps_path=self.apps_path)
		self.assertEqual(result["created"], ["sections/testimonials.html", "sections/testimonials.json"])
		schema = json.loads(self.read_theme_file("sections/testimonials.json"))
		schema_path = os.path.join(self.theme_dir, "sections", schema.pop("$schema"))
		self.assertTrue(
			os.path.samefile(schema_path, frappe.get_app_path("commera", "themes", "section.schema.json"))
		)
		self.assertEqual(
			schema,
			{
				"name": "Testimonials",
				"settings": [{"id": "heading", "type": "text", "label": "Heading", "translatable": True}],
				"blocks": {
					"quote": {
						"name": "Quote",
						"settings": [
							{"id": "text", "type": "textarea", "label": "Text", "translatable": True}
						],
					}
				},
				"presets": [{"blocks": ["quote"]}],
			},
		)
		self.assert_theme_clean()

		create_block("atelier", "testimonials", "rating", apps_path=self.apps_path)
		create_block("atelier", "testimonials", "badge", static=True, apps_path=self.apps_path)
		template = self.read_theme_file("sections/testimonials.html")
		self.assertEqual(template.count("<div{{ block.editor_attributes }}>"), 3)
		self.assertLess(template.index("macro badge(block)"), template.index("for block in section.blocks"))
		blocks = json.loads(self.read_theme_file("sections/testimonials.json"))["blocks"]
		self.assertEqual(list(blocks), ["quote", "rating", "badge"])
		self.assertTrue(blocks["badge"]["static"])
		self.assert_theme_clean()

	def test_static_group_and_controller_sections_stay_clean(self):
		result = create_section(
			"atelier", "main_page", static=True, templates=["page"], controller=True, apps_path=self.apps_path
		)
		self.assertIn("sections/main_page.py", result["created"])
		self.assertEqual(
			json.loads(self.read_theme_file("layouts/page.json"))["sections"][-1]["type"], "main_page"
		)
		create_section("atelier", "announcement", ["message"], group="header", apps_path=self.apps_path)
		create_block("atelier", "announcement", "link_text", apps_path=self.apps_path)
		self.assert_theme_clean()

	def test_refuses_bad_sections_and_blocks(self):
		create_section("atelier", "testimonials", ["quote"], apps_path=self.apps_path)
		cases = {
			"unknown theme": lambda: create_section("no_such_theme", "promo", apps_path=self.apps_path),
			"type already in the chain": lambda: create_section("atelier", "hero", apps_path=self.apps_path),
			"type not snake_case": lambda: create_section("atelier", "Promo", apps_path=self.apps_path),
			"reserved block": lambda: create_section(
				"atelier", "picks", ["product"], apps_path=self.apps_path
			),
			"unknown template": lambda: create_section(
				"atelier", "promo", templates=["home"], apps_path=self.apps_path
			),
			"block on an inherited section": lambda: create_block(
				"atelier", "hero", "slide", apps_path=self.apps_path
			),
			"duplicate block": lambda: create_block(
				"atelier", "testimonials", "quote", apps_path=self.apps_path
			),
		}
		for case, create in cases.items():
			with self.subTest(case), self.assertRaises(click.UsageError):
				create()
		self.assertFalse(os.path.exists(os.path.join(self.theme_dir, "sections", "picks.json")))
