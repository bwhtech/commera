import importlib.util
import json
import tempfile
from pathlib import Path

import click
import frappe
from frappe.tests import UnitTestCase
from frappe.utils.boilerplate import _create_app_boilerplate

from commera.plugins.places import ICONS, PLACES
from commera.scaffold import PLACE_KINDS, AppScaffold, get_app_from_folder, get_dashboard_versions
from commera.sdk import API_VERSION

APP = "commera_test_plugin"


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


def get_hooks(app_root: Path) -> dict:
	namespace = {}
	exec((app_root / APP / "hooks.py").read_text(), namespace)
	return namespace


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

		package = json.loads((app_root / "package.json").read_text())
		self.assertEqual(package["scripts"]["build"], "vite build --config commera/vite.config.js")
		self.assertNotIn("dev", package["scripts"])
		self.assertEqual(
			package["devDependencies"],
			{"@commera/plugin-kit": "link:../commera/packages/plugin-kit", **get_dashboard_versions()},
		)
		self.assertEqual((app_root / ".gitignore").read_text(), f"node_modules\n{APP}/public/commera/\n")

		page = app_root / "commera" / "pages" / "commera-test-plugin" / "index.vue"
		self.assertIn("export const plugin = { label: 'Test Plugin', icon: 'sparkles' }", page.read_text())
		self.assertIn("sparkles", ICONS)
		self.assertIn(f"useMethodRead('{APP}.api.get_summary')", page.read_text())
		self.assertIn(f"{APP}/api.py", created)
		for place in PLACES:
			if place != "pages":
				self.assertTrue((app_root / "commera" / place / ".gitkeep").is_file(), place)
		self.assertIn(f"bench build --app {APP}", (app_root / "commera" / "README.md").read_text())
		self.assertIn("commera/vite.config.js", created)
		self.assertNotIn(f"{APP}/public/.gitkeep", created)

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
			"\ndoc_events = {}\n",
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
		self.assertEqual({place for place, _starter in PLACE_KINDS.values()}, set(PLACES))

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

	def test_an_existing_placement_or_method_is_not_overwritten(self):
		self.add("order-card", "status")
		with self.assertRaisesRegex(click.ClickException, "already exists"):
			self.add("order-card", "status")
		self.add("order-action", "resend")
		(self.app_root / "commera" / "order/actions/resend").rename(self.app_root / "commera" / "moved")
		with self.assertRaisesRegex(click.ClickException, "already has resend_order"):
			self.add("order-action", "resend")

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
