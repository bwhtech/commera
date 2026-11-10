import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import click
import frappe
from frappe.modules.import_file import import_file_by_path
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils.boilerplate import _create_app_boilerplate
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.commands import get_current_app_scaffold
from commera.localization import get_localization
from commera.plugins.places import ICONS, PLACES
from commera.scaffold import (
	LOGO_COLOURS,
	PLACE_KINDS,
	AppScaffold,
	get_app_from_folder,
	get_dashboard_versions,
)
from commera.scaffold.shipping_provider import ShippingProviderScaffold
from commera.scaffold.theme import ThemeScaffold
from commera.sdk import API_VERSION
from commera.shipping.base_class import ShippingProviderBase
from commera.shop_themes.sections import get_theme_json, validate_layout
from commera.tests.test_localization import use_storefront_languages

APP = "commera_test_plugin"
STARTER = "Commera Starter"
STARTER_SETTINGS = "Commera Starter Settings"
STARTER_DIRS = {
	"themes": Path(frappe.get_app_path("commera"), "themes", "commera_starter"),
	"public/themes": Path(frappe.get_app_path("commera"), "public", "themes", "commera_starter"),
}
JINJA_COMMENT = re.compile(r"{#.*?#}", re.DOTALL)
# A language prefix glued on by hand instead of through url() or switch_url().
HAND_BUILT_PREFIX = re.compile(r'root_prefix|language\.code\s*~|~\s*localization|href="/(?!assets/|files/)')
PHYSICAL_CSS = re.compile(
	r"\b(margin|padding)-(left|right)\b|text-align:\s*(left|right)|[\s{;](left|right)\s*:"
)


def make_app(apps_path: Path, app: str = APP) -> Path:
	hooks = frappe._dict(
		app_name=app,
		app_title="Test Plugin",
		app_description="",
		app_publisher="",
		app_email="",
		app_license="mit",
		create_github_workflow=False,
		branch_name="develop",
	)
	_create_app_boilerplate(str(apps_path), hooks, no_git=True)
	return apps_path / app


def read_tree(root: Path) -> dict[str, str]:
	return {
		str(path.relative_to(root)): path.read_text() for path in sorted(root.rglob("*")) if path.is_file()
	}


def list_files(root: Path) -> set[str]:
	return {
		str(path.relative_to(root))
		for path in root.rglob("*")
		if path.is_file() and "__pycache__" not in path.parts and "node_modules" not in path.parts
	}


def read_templates(theme_dir: Path) -> str:
	text = "".join(path.read_text() for path in sorted(theme_dir.rglob("*.html")))
	return JINJA_COMMENT.sub("", text)


def get_fieldnames(doctype: dict) -> list[str]:
	return [field["fieldname"] for field in doctype["fields"]]


def get_hooks(app_root: Path) -> dict:
	namespace = {}
	exec((app_root / APP / "hooks.py").read_text(), namespace)
	return namespace


def forget_app_modules():
	for name in [name for name in sys.modules if name == APP or name.startswith(f"{APP}.")]:
		sys.modules.pop(name)


class TestScaffold(UnitTestCase):
	def setUp(self):
		self.directory = tempfile.TemporaryDirectory()
		self.apps_path = Path(self.directory.name)
		self.addCleanup(self.directory.cleanup)

	def test_scaffold_adds_every_piece_to_a_new_app(self):
		app_root = make_app(self.apps_path)
		created = {path for change, path in AppScaffold(APP, self.apps_path).save() if change == "created"}

		hooks = get_hooks(app_root)
		self.assertEqual(hooks["required_apps"], ["commera"])
		self.assertEqual(hooks["commera_api_version"], [API_VERSION])
		self.assertEqual(hooks["commera_plugin_title"], "Test Plugin")

		package = json.loads((app_root / "package.json").read_text())
		self.assertEqual(package["scripts"]["build"], "vite build --config commera/vite.config.js")
		self.assertNotIn("dev", package["scripts"])
		self.assertEqual(
			package["devDependencies"],
			{"@commera/plugin-kit": "link:../commera/packages/plugin-kit", **get_dashboard_versions()},
		)
		self.assertEqual((app_root / ".gitignore").read_text(), f"node_modules\n{APP}/public/commera/\n")

		page = app_root / "commera" / "pages" / "commera-test-plugin" / "index.vue"
		self.assertIn("export const plugin = { label: 'Test Plugin' }", page.read_text())
		logo = (app_root / "commera" / "plugin-icon.svg").read_text()
		self.assertTrue(any(f'fill="{colour}"' in logo for colour in LOGO_COLOURS), logo)
		self.assertIn("sparkles", ICONS)
		self.assertIn(f"useMethodRead('{APP}.api.get_summary')", page.read_text())
		self.assertIn(f"{APP}/api.py", created)
		for place, spec in PLACES.items():
			if spec.get("config"):
				self.assertFalse((app_root / "commera" / place).exists(), place)
			elif place != "pages":
				self.assertTrue((app_root / "commera" / place / ".gitkeep").is_file(), place)
		self.assertIn(f"bench build --app {APP}", (app_root / "commera" / "README.md").read_text())
		self.assertIn("commera/vite.config.js", created)
		self.assertNotIn(f"{APP}/public/.gitkeep", created)

	def test_packages_are_installed_before_the_plugin_folder_appears(self):
		app_root = make_app(self.apps_path)
		seen = {}

		def install(command, cwd, check):
			seen.update(package=(app_root / "package.json").exists(), source=(app_root / "commera").exists())

		with patch("commera.scaffold.subprocess.run", side_effect=install) as run:
			AppScaffold(APP, self.apps_path).save(install=True)

		run.assert_called_once_with(["yarn", "install"], cwd=app_root, check=True)
		self.assertEqual(seen, {"package": True, "source": False})
		self.assertTrue((app_root / "commera" / "vite.config.js").exists())

	def test_second_scaffold_changes_nothing(self):
		app_root = make_app(self.apps_path)
		AppScaffold(APP, self.apps_path).save()
		before = read_tree(app_root)

		changes = AppScaffold(APP, self.apps_path).save()

		self.assertEqual({change for change, path in changes}, {"skipped"})
		self.assertEqual(read_tree(app_root), before)

	def test_scaffold_keeps_existing_files_and_adds_missing_entries(self):
		app_root = make_app(self.apps_path)
		hooks_path = app_root / APP / "hooks.py"
		hooks_path.write_text(
			hooks_path.read_text().replace("# required_apps = []", 'required_apps = ["erpnext"]')
		)
		(app_root / ".gitignore").write_text("node_modules/\n*.pyc")
		(app_root / "package.json").write_text(json.dumps({"name": APP, "scripts": {"build": "custom"}}))
		(app_root / "commera" / "pages" / "jobs").mkdir(parents=True)
		(app_root / APP / "api.py").write_text("import frappe\n")

		AppScaffold(APP, self.apps_path).save()

		self.assertEqual(get_hooks(app_root)["required_apps"], ["erpnext", "commera"])
		self.assertEqual(get_hooks(app_root)["commera_api_version"], [API_VERSION])
		self.assertEqual(
			(app_root / ".gitignore").read_text(),
			f"node_modules/\n*.pyc\nnode_modules\n{APP}/public/commera/\n",
		)
		package = json.loads((app_root / "package.json").read_text())
		self.assertEqual(package["scripts"]["build"], "custom")
		self.assertIn("@commera/plugin-kit", package["devDependencies"])
		self.assertEqual(
			list((app_root / "commera" / "pages").iterdir()), [app_root / "commera" / "pages" / "jobs"]
		)
		self.assertEqual((app_root / APP / "api.py").read_text(), "import frappe\n")

	def test_the_starter_api_is_whitelisted_and_checks_permission(self):
		app_root = make_app(self.apps_path)
		AppScaffold(APP, self.apps_path).save()
		# Named inside commera because a whitelisted call looks up the hooks of its module's app.
		spec = importlib.util.spec_from_file_location("commera.starter_api", app_root / APP / "api.py")
		api = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(api)

		self.assertIn(api.get_summary, frappe.whitelisted)
		self.assertIsInstance(api.get_summary()["orders_today"], int)
		with self.set_user("Guest"), self.assertRaises(frappe.PermissionError):
			api.get_summary()

	def test_hooks_without_the_boilerplate_comment_get_commera_after_the_app_metadata(self):
		app_root = make_app(self.apps_path)
		hooks_path = app_root / APP / "hooks.py"
		hooks_path.write_text('app_name = "x"\napp_title = "X"\n\ndoc_events = {}\n')

		AppScaffold(APP, self.apps_path).save()

		self.assertEqual(
			hooks_path.read_text(),
			f'app_name = "x"\napp_title = "X"\nrequired_apps = ["commera"]\ncommera_api_version = [{API_VERSION}]\n'
			'commera_plugin_title = "X"\n\ndoc_events = {}\n',
		)

	def test_scaffold_refuses_commera_and_missing_apps(self):
		make_app(self.apps_path)
		with self.assertRaisesRegex(click.ClickException, "host app"):
			AppScaffold("commera", self.apps_path)
		with self.assertRaisesRegex(click.ClickException, "not a Frappe app"):
			AppScaffold("no_such_app", self.apps_path)
		with self.assertRaisesRegex(click.ClickException, "not a Frappe app"):
			AppScaffold(APP, self.apps_path / APP)

	def test_init_finds_the_app_from_any_folder_inside_it(self):
		app_root = make_app(self.apps_path)
		self.assertEqual(get_app_from_folder(app_root, self.apps_path), APP)
		self.assertEqual(get_app_from_folder(app_root / APP / "public", self.apps_path), APP)

	def test_init_outside_an_app_folder_says_where_to_run_it(self):
		for folder in (self.apps_path, self.apps_path.parent):
			with self.assertRaisesRegex(click.ClickException, "cd apps/<your_app>"):
				get_app_from_folder(folder, self.apps_path)


class TestAddPlace(UnitTestCase):
	def setUp(self):
		self.directory = tempfile.TemporaryDirectory()
		self.apps_path = Path(self.directory.name)
		self.addCleanup(self.directory.cleanup)
		self.app_root = make_app(self.apps_path)
		AppScaffold(APP, self.apps_path).save()

	def add(self, kind: str, name: str | None = None) -> list[tuple[str, str]]:
		return AppScaffold(APP, self.apps_path).add_place(kind, name)

	def test_every_placement_folder_has_a_kind(self):
		# Config places (sidebar actions) live in commera/plugin.config.ts, so `add` writes no folder for them.
		folder_places = {place for place, spec in PLACES.items() if not spec.get("config")}
		self.assertEqual({place for place, _starter in PLACE_KINDS.values()}, folder_places)

	def test_each_kind_writes_its_placement_with_a_plugin_block(self):
		for kind, (place, _starter) in PLACE_KINDS.items():
			name = None if kind == "settings" else "first-one"
			self.add(kind, name)
			folder = "settings" if kind == "settings" else f"{place}/first-one"
			source = (self.app_root / "commera" / folder / "index.vue").read_text()
			self.assertIn("export const plugin = {", source, kind)
			self.assertNotIn("$", source.replace("${", ""), kind)

	def test_an_action_gets_a_whitelisted_method_that_checks_the_record(self):
		self.add("order-action", "resend")

		page = (self.app_root / "commera" / "order/actions/resend/index.vue").read_text()
		self.assertIn(f"method: '{APP}.api.resend_order'", page)
		api = self.load_api()
		self.assertIn(api.resend_order, frappe.whitelisted)
		with self.assertRaises(frappe.DoesNotExistError):
			api.resend_order(name="no-such-order")

	def test_a_command_gets_a_method_without_arguments(self):
		self.add("command", "sync-now")

		self.assertEqual(self.load_api().sync_now(), "Sync now ran")

	def test_settings_gets_a_sidebar_row_that_opens_it(self):
		self.add("settings")

		config = (self.app_root / "commera" / "plugin.config.ts").read_text()
		self.assertIn("definePlugin({", config)
		self.assertIn("name: 'settings'", config)
		self.assertIn("openSettings()", config)

	def test_an_existing_plugin_config_is_kept(self):
		config = self.app_root / "commera" / "plugin.config.ts"
		config.write_text("export default {}\n")

		changes = self.add("settings")

		self.assertIn(("skipped", "commera/plugin.config.ts"), changes)
		self.assertEqual(config.read_text(), "export default {}\n")

	def test_an_existing_placement_or_method_is_not_overwritten(self):
		self.add("order-card", "status")
		with self.assertRaisesRegex(click.ClickException, "already exists"):
			self.add("order-card", "status")
		self.add("order-action", "resend")
		(self.app_root / "commera" / "order/actions/resend").rename(self.app_root / "commera" / "moved")
		with self.assertRaisesRegex(click.ClickException, "already has resend_order"):
			self.add("order-action", "resend")

	def test_a_page_with_detail_gets_a_detail_view_that_its_list_opens(self):
		AppScaffold(APP, self.apps_path).add_place("page", "jobs", detail=True)

		folder = self.app_root / "commera" / "pages" / "jobs"
		self.assertIn("navigate('jobs/EXAMPLE-0001')", (folder / "index.vue").read_text())
		self.assertIn("defineProps({ id: String })", (folder / "[...id].vue").read_text())

	def test_only_a_page_takes_detail(self):
		with self.assertRaisesRegex(click.ClickException, "only goes with a page"):
			AppScaffold(APP, self.apps_path).add_place("order-card", "status", detail=True)

	def test_a_bad_kind_or_name_is_refused(self):
		with self.assertRaisesRegex(click.ClickException, "Add one of: page, order-card"):
			self.add("orders-card", "status")
		with self.assertRaisesRegex(click.ClickException, "lowercase letters"):
			self.add("page", "Print_Jobs")
		with self.assertRaisesRegex(click.ClickException, "lowercase letters"):
			self.add("page")

	def load_api(self):
		spec = importlib.util.spec_from_file_location("commera.starter_api", self.app_root / APP / "api.py")
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)
		return module


class IntegrationTestThemeScaffold(IntegrationTestCase):
	def setUp(self):
		directory = tempfile.TemporaryDirectory()
		self.addCleanup(directory.cleanup)
		self.apps_path = Path(directory.name)
		app_root = make_app(self.apps_path)
		sys.path.insert(0, str(app_root))
		self.addCleanup(sys.path.remove, str(app_root))
		forget_app_modules()
		self.addCleanup(forget_app_modules)
		self.module = frappe.get_module_list(APP)[0]
		frappe.local.module_app[frappe.scrub(self.module)] = APP
		self.addCleanup(frappe.local.module_app.pop, frappe.scrub(self.module))
		self.addCleanup(frappe.db.rollback)
		frappe.db.set_value("Shop Theme", {"use_as_starter": 1}, "use_as_starter", 0)
		frappe.db.set_value("Shop Theme", STARTER, "use_as_starter", 1)
		self.theme_dir = app_root / APP / "themes" / "scaffold_check"
		self.export_path = (
			app_root
			/ APP
			/ frappe.scrub(self.module)
			/ "shop_theme"
			/ "scaffold_check"
			/ "scaffold_check.json"
		)

	def test_a_theme_can_be_added_to_commera_by_name(self):
		scaffold = get_current_app_scaffold(ThemeScaffold, "commera")
		self.assertEqual(scaffold.app, "commera")
		self.assertEqual(scaffold.get_theme_module(), "Shop Themes")

	def test_an_uninstalled_app_gets_the_files_and_the_record_on_install(self):
		changes = ThemeScaffold(APP, self.apps_path).add_theme(
			"Scaffold Check", "Sections", "Shop Base Theme"
		)

		self.assertTrue((self.theme_dir / "README.md").is_file())
		self.assertTrue((self.theme_dir / "layouts" / "index.json").is_file())
		self.assertIn(("created", str(self.export_path.relative_to(self.apps_path / APP))), changes)
		self.assertFalse(frappe.db.exists("Shop Theme", "Scaffold Check"))

		frappe.get_doc({"doctype": "Module Def", "module_name": self.module, "app_name": APP}).insert()
		import_file_by_path(str(self.export_path))
		self.assertEqual(
			frappe.db.get_value(
				"Shop Theme", "Scaffold Check", ["theme_type", "parent_theme", "module", "is_standard"]
			),
			("Sections", "Shop Base Theme", self.module, 1),
		)

	def test_a_theme_lands_where_the_app_is_imported_from(self):
		directory = tempfile.TemporaryDirectory()
		self.addCleanup(directory.cleanup)
		worktree = make_app(Path(directory.name))
		sys.path.insert(0, str(worktree))
		self.addCleanup(sys.path.remove, str(worktree))
		forget_app_modules()

		changes = ThemeScaffold(APP, self.apps_path).add_theme(
			"Scaffold Check", "Sections", "Shop Base Theme"
		)

		export_path = worktree / self.export_path.relative_to(self.apps_path / APP)
		self.assertTrue(export_path.is_file())
		self.assertIn(("created", str(export_path.relative_to(worktree))), changes)

	def test_an_uninstalled_app_still_checks_the_parent(self):
		scaffold = ThemeScaffold(APP, self.apps_path)
		with self.assertRaisesRegex(click.ClickException, "does not exist"):
			scaffold.add_theme("Scaffold Check", "Sections", "No Such Theme")
		with self.assertRaisesRegex(click.ClickException, "can only inherit"):
			scaffold.add_theme("Scaffold Check", "Classic", "Summer Theme")
		self.assertFalse(self.theme_dir.exists())

	def assert_starter_copy(self):
		for folder, starter_dir in STARTER_DIRS.items():
			copy_dir = self.theme_dir.parents[1] / folder / "scaffold_check"
			self.assertEqual(list_files(copy_dir), list_files(starter_dir))
			for path in copy_dir.rglob("*"):
				if path.is_file() and path.suffix in (".css", ".html", ".js", ".json", ".md", ".py"):
					text = path.read_text()
					self.assertNotIn("commera_starter", text, path)
					self.assertNotIn("Commera Starter", text, path)
		self.assertTrue((self.theme_dir / "README.md").read_text().startswith("# Scaffold Check\n"))
		self.assert_localized(self.theme_dir)

	def assert_localized(self, theme_dir):
		templates = read_templates(theme_dir)
		for call in ("url(", "_(", "localization", "language_switcher("):
			self.assertIn(call, templates)
		self.assertNotRegex(templates, HAND_BUILT_PREFIX)
		self.assertNotRegex(templates, PHYSICAL_CSS)

	def test_a_minimal_theme_links_through_url_and_localization(self):
		frappe.db.set_value("Shop Theme", STARTER, "use_as_starter", 0)

		for theme_type in ("Classic", "Sections"):
			with self.subTest(theme_type):
				ThemeScaffold(APP, self.apps_path).add_theme(f"Scaffold {theme_type}", theme_type, None)
				theme_dir = self.theme_dir.parent / f"scaffold_{theme_type.lower()}"
				self.assert_localized(theme_dir)
				for href in re.findall(r'href="([^"]*)"', read_templates(theme_dir)):
					self.assertRegex(href, r"^\{\{ url\(")

	def test_minimal_theme_links_carry_the_page_language(self):
		frappe.db.set_value("Shop Theme", STARTER, "use_as_starter", 0)
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		frappe.local.request = Request(EnvironBuilder(path="/ar/").get_environ())
		ThemeScaffold(APP, self.apps_path).add_theme("Scaffold Check", "Classic", None)
		ThemeScaffold(APP, self.apps_path).add_theme("Scaffold Sections", "Sections", None)

		header = self.render(self.theme_dir / "components" / "includes" / "header.html")
		section = self.render(
			self.theme_dir.parent / "scaffold_sections" / "sections" / "rich_text.html",
			section={"settings": {"button_label": "Shop", "button_url": "/products"}},
		)

		self.assertIn('href="/ar/products"', header)
		self.assertIn('hreflang="en"', header)
		self.assertIn('href="/ar/products"', section)

	def render(self, path: Path, **context) -> str:
		# nosemgrep: frappe-ssti
		return frappe.render_template(path.read_text(), {"localization": get_localization(), **context})

	def test_a_sections_theme_without_a_parent_is_a_copy_of_the_starter(self):
		changes = ThemeScaffold(APP, self.apps_path).add_theme("Scaffold Check", "Sections", None)

		self.assert_starter_copy()
		settings_dir = self.export_path.parents[2] / "doctype" / "scaffold_check_settings"
		settings = json.loads((settings_dir / "scaffold_check_settings.json").read_text())
		starter_settings = frappe.get_meta(STARTER_SETTINGS)
		self.assertEqual(settings["name"], "Scaffold Check Settings")
		self.assertEqual(settings["module"], self.module)
		self.assertEqual(settings["issingle"], 1)
		self.assertEqual(get_fieldnames(settings), [field.fieldname for field in starter_settings.fields])
		self.assertTrue((settings_dir / "scaffold_check_settings.py").is_file())
		self.assertIn(("created", str(settings_dir.relative_to(self.apps_path / APP))), changes)

		self.assertNotIn("__islocal", settings)
		theme = json.loads(self.export_path.read_text())
		self.assertEqual(theme["theme_settings"], "Scaffold Check Settings")
		self.assertNotIn("parent_theme", theme)

		frappe.get_doc({"doctype": "Module Def", "module_name": self.module, "app_name": APP}).insert()
		import_file_by_path(str(settings_dir / "scaffold_check_settings.json"))
		import_file_by_path(str(self.export_path))
		self.assertEqual(
			frappe.db.get_value("Shop Theme", "Scaffold Check", "theme_settings"), "Scaffold Check Settings"
		)
		self.assertEqual(
			[field.fieldname for field in frappe.get_meta("Scaffold Check Settings").fields],
			[field.fieldname for field in starter_settings.fields],
		)

	def test_a_desk_sections_theme_without_a_parent_gets_its_own_settings(self):
		frappe.get_doc({"doctype": "Module Def", "module_name": self.module, "app_name": APP}).insert()
		theme = frappe.new_doc("Shop Theme")
		theme.update({"theme_name": "Scaffold Check", "theme_type": "Sections", "module": self.module})
		with patch.dict(frappe.conf, {"developer_mode": 1}):
			theme.insert()

		self.assert_starter_copy()
		self.assertEqual(theme.theme_settings, "Scaffold Check Settings")
		self.assertEqual(theme.is_standard, 1)
		self.assertEqual(
			json.loads(self.export_path.read_text())["theme_settings"], "Scaffold Check Settings"
		)
		self.assertEqual(
			[field.fieldname for field in frappe.get_meta("Scaffold Check Settings").fields],
			[field.fieldname for field in frappe.get_meta(STARTER_SETTINGS).fields],
		)
		theme_context = {
			"theme_name": "Scaffold Check",
			"theme_type": "Sections",
			"names": ["Scaffold Check"],
			"dirs": [str(self.theme_dir)],
			"apps": {"Scaffold Check": APP},
			"settings_doctype": "Scaffold Check Settings",
		}
		for page in ("index", "header_group", "footer_group"):
			with self.subTest(page):
				layout = get_theme_json([str(self.theme_dir)], f"layouts/{page}.json")
				validate_layout(theme_context, layout, page)

	def test_an_installed_app_lists_the_settings_doctype_it_created(self):
		frappe.get_doc({"doctype": "Module Def", "module_name": self.module, "app_name": APP}).insert()
		with patch.object(ThemeScaffold, "is_installed", return_value=True):
			changes = ThemeScaffold(APP, self.apps_path).add_theme("Scaffold Check", "Sections", None)

		settings_dir = self.export_path.parents[2] / "doctype" / "scaffold_check_settings"
		self.assertIn(("created", str(settings_dir.relative_to(self.apps_path / APP))), changes)
		self.assertEqual(
			frappe.db.get_value("Shop Theme", "Scaffold Check", "theme_settings"), "Scaffold Check Settings"
		)

	def test_a_sections_theme_with_a_parent_stays_minimal(self):
		ThemeScaffold(APP, self.apps_path).add_theme("Scaffold Check", "Sections", "Shop Base Theme")

		self.assertFalse((self.theme_dir / "components").exists())
		self.assertFalse((self.export_path.parents[2] / "doctype" / "scaffold_check_settings").exists())
		self.assertNotIn("theme_settings", json.loads(self.export_path.read_text()))

	def insert_desk_theme(self, theme_name):
		theme = frappe.new_doc("Shop Theme")
		theme.update({"theme_name": theme_name, "theme_type": "Sections", "module": self.module})
		with patch.dict(frappe.conf, {"developer_mode": 1}):
			theme.insert()
		return theme

	def test_no_ticked_starter_gives_minimal_folders(self):
		frappe.db.set_value("Shop Theme", STARTER, "use_as_starter", 0)

		ThemeScaffold(APP, self.apps_path).add_theme("Scaffold Check", "Sections", None)

		self.assertTrue((self.theme_dir / "layouts" / "index.json").is_file())
		self.assertFalse((self.theme_dir / "components").exists())
		self.assertFalse((self.export_path.parents[2] / "doctype" / "scaffold_check_settings").exists())
		self.assertNotIn("theme_settings", json.loads(self.export_path.read_text()))

	def test_a_second_starter_for_one_theme_type_is_refused(self):
		frappe.get_doc({"doctype": "Module Def", "module_name": self.module, "app_name": APP}).insert()
		theme = self.insert_desk_theme("Scaffold Check")

		theme.use_as_starter = 1
		with self.assertRaisesRegex(frappe.ValidationError, f"{STARTER} is already the Sections starter"):
			theme.save()

		theme.reload()
		theme.update({"use_as_starter": 1, "is_standard": 0})
		frappe.db.set_value("Shop Theme", STARTER, "use_as_starter", 0)
		with self.assertRaisesRegex(frappe.ValidationError, "Only a standard theme"):
			theme.save()

	def test_the_copy_follows_the_ticked_starter(self):
		frappe.get_doc({"doctype": "Module Def", "module_name": self.module, "app_name": APP}).insert()
		starter = self.insert_desk_theme("Scaffold Check")
		(self.theme_dir / "notes.md").write_text("Scaffold Check notes")
		starter_settings = frappe.get_doc("DocType", "Scaffold Check Settings")
		starter_settings.append(
			"fields", {"fieldname": "scaffold_note", "fieldtype": "Data", "label": "Note"}
		)
		with patch.dict(frappe.conf, {"developer_mode": 1}):
			starter_settings.save()
			frappe.db.set_value("Shop Theme", STARTER, "use_as_starter", 0)
			starter.use_as_starter = 1
			starter.save()

		ThemeScaffold(APP, self.apps_path).add_theme("Scaffold Copy", "Sections", None)

		copy_dir = self.theme_dir.parent / "scaffold_copy"
		self.assertEqual(list_files(copy_dir), list_files(self.theme_dir))
		self.assertEqual((copy_dir / "notes.md").read_text(), "Scaffold Copy notes")
		settings_dir = self.export_path.parents[2] / "doctype" / "scaffold_copy_settings"
		settings = json.loads((settings_dir / "scaffold_copy_settings.json").read_text())
		self.assertEqual(
			get_fieldnames(settings),
			[field.fieldname for field in frappe.get_meta("Scaffold Check Settings").fields],
		)
		self.assertIn("scaffold_note", get_fieldnames(settings))


class TestShippingProviderScaffold(UnitTestCase):
	def setUp(self):
		directory = tempfile.TemporaryDirectory()
		self.addCleanup(directory.cleanup)
		self.app_root = make_app(Path(directory.name))
		self.scaffold = ShippingProviderScaffold(APP, Path(directory.name))
		self.folder = self.app_root / APP / frappe.scrub(self.scaffold.get_module()) / "doctype"

	def load_controller(self):
		path = self.folder / "delhivery_shipping_settings" / "delhivery_shipping_settings.py"
		spec = importlib.util.spec_from_file_location("delhivery_shipping_settings", path)
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)
		return module.DelhiveryShippingSettings

	def test_a_new_carrier_gets_a_settings_single_registered_in_commera_hooks(self):
		self.scaffold.add_shipping_provider("Delhivery")

		hooks = get_hooks(self.app_root)
		settings = json.loads(
			(self.folder / "delhivery_shipping_settings" / "delhivery_shipping_settings.json").read_text()
		)
		controller = self.load_controller()
		self.assertEqual(hooks["commera_hooks"], {"shipping_providers": ["Delhivery Shipping Settings"]})
		self.assertIn("commera", hooks["required_apps"])
		self.assertEqual(hooks["commera_api_version"], [API_VERSION])
		self.assertEqual((settings["name"], settings["issingle"]), ("Delhivery Shipping Settings", 1))
		self.assertTrue(issubclass(controller, ShippingProviderBase))
		self.assertEqual(controller.label, "Delhivery")
		self.assertFalse(controller.supports("booking"))

	def test_existing_commera_hooks_keep_their_entries(self):
		hooks_path = self.app_root / APP / "hooks.py"
		hooks_path.write_text(
			hooks_path.read_text() + '\ncommera_hooks = {"cart_fees": ["commera_test_plugin.fees"]}\n'
		)

		self.scaffold.add_shipping_provider("Delhivery")
		self.scaffold.add_shipping_provider("Bluedart")

		self.assertEqual(
			get_hooks(self.app_root)["commera_hooks"],
			{
				"cart_fees": ["commera_test_plugin.fees"],
				"shipping_providers": ["Delhivery Shipping Settings", "Bluedart Shipping Settings"],
			},
		)

	def test_a_taken_or_bad_name_is_refused(self):
		self.scaffold.add_shipping_provider("Delhivery")

		self.assertRaises(click.ClickException, self.scaffold.add_shipping_provider, "Delhivery")
		self.assertRaises(click.ClickException, self.scaffold.add_shipping_provider, "Del-hivery!")
