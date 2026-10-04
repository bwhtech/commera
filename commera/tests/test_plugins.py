# Copyright (c) 2026, company@bwhstudios.com and Contributors

import hashlib
import json
import os
import shutil
import sys
import tempfile
from types import ModuleType
from unittest.mock import patch

import frappe
from frappe.core.doctype.sms_settings.sms_settings import SMSSettings
from frappe.core.doctype.user_permission.test_user_permission import create_user
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime
from frappe.utils.password import get_decrypted_password

from commera.api.admin.plugins import (
	get_plugin_deliveries,
	get_plugin_settings,
	get_plugins,
	get_record_plugins,
	run_command,
	run_record_action,
	save_plugin_setting,
)
from commera.plugins import registry
from commera.plugins.places import GRAMMAR, PLACES, RECORD_DOCTYPES
from commera.plugins.registry import get_registry, get_visible_plugins
from commera.sdk import API_VERSION
from commera.tests.test_admin_order_plugin_events import make_order_event
from commera.tests.test_admin_orders import make_test_sales_order
from commera.tests.test_plugin_events import patch_app_declarations
from commera.www import commera as dashboard

APP = "bwh_shipping"
OTHER_APP = "bwh_payments"
FUNCTIONS = f"{APP}.commera_test_plugins"
SETTINGS_DOCTYPE = "Google Settings"
REQUIRED_SETTINGS_DOCTYPE = "SMS Settings"
STOCK_USER = "plugins-stock@example.com"
SALES_USER = "plugins-sales@example.com"
OUTSIDER = "plugins-outsider@example.com"
SYSTEM_MANAGER = "plugins-admin@example.com"


def show_record(doctype, name):
	return True


def hide_record(doctype, name):
	return False


def show_page():
	return True


def hide_page():
	return False


def raise_error(*arguments):
	raise ValueError("condition broke")


@frappe.whitelist(methods=["POST"])
def resend_order(name):
	return f"Resent {name}"


def unlisted_method(name):
	return "never runs"


@frappe.whitelist(methods=["POST"])
def sync_orders():
	return "Synced 3 orders"


@frappe.whitelist(methods=["POST"])
def sync_quietly():
	return {"synced": 3}


def page(name="jobs", **fields) -> dict:
	return {
		"place": "pages",
		"name": name,
		"module": f"pages/{name}.js",
		"hash": "9f2c1a",
		"label": "Print jobs",
		"icon": "printer",
		**fields,
	}


def card(name="print-status", place="order/cards", **fields) -> dict:
	return {
		"place": place,
		"name": name,
		"module": f"{place}/{name}.js",
		"hash": "1",
		"label": "Print status",
		**fields,
	}


def action(name="resend", place="order/actions", **fields) -> dict:
	return {
		"place": place,
		"name": name,
		"module": None,
		"label": "Resend to printer",
		"method": f"{FUNCTIONS}.resend_order",
		"confirm": "Send it again?",
		**fields,
	}


def command(name="sync", **fields) -> dict:
	return {
		"place": "commands",
		"name": name,
		"module": None,
		"label": "Sync orders",
		"keywords": ["printer"],
		"method": f"{FUNCTIONS}.sync_orders",
		**fields,
	}


def app_settings(**fields) -> dict:
	return {
		"place": "settings",
		"name": "settings",
		"module": None,
		"label": "Shipping",
		"doctype": SETTINGS_DOCTYPE,
		**fields,
	}


def error_logged(title: str, since) -> bool:
	return bool(frappe.db.exists("Error Log", {"method": title, "creation": [">=", since]}))


@patch.dict(frappe.conf, {"developer_mode": 1})
class PluginTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		create_user(STOCK_USER, "Item Manager", "Stock User")
		create_user(SALES_USER, "Sales User")
		create_user(OUTSIDER, "Item Manager")
		create_user(SYSTEM_MANAGER, "Stock User", "Sales User", "System Manager")

	def setUp(self):
		self.started_at = now_datetime()
		self.assets_folder = tempfile.mkdtemp()
		self.addCleanup(shutil.rmtree, self.assets_folder, ignore_errors=True)
		asset_path = patch.object(
			registry,
			"get_asset_path",
			side_effect=lambda app, relative_path: os.path.join(self.assets_folder, app, relative_path),
		)
		asset_path.start()
		self.addCleanup(asset_path.stop)
		self.declare_apps({APP: [API_VERSION], OTHER_APP: [API_VERSION]})

		module = ModuleType(FUNCTIONS)
		for function in (
			show_record,
			hide_record,
			show_page,
			hide_page,
			raise_error,
			resend_order,
			sync_orders,
			sync_quietly,
		):
			setattr(module, function.__name__, function)
		module.unlisted_method = unlisted_method
		sys.modules[FUNCTIONS] = module
		self.addCleanup(sys.modules.pop, FUNCTIONS, None)

	def declare_apps(self, api_versions_by_app: dict):
		patch_app_declarations(
			self,
			{
				app: {"commera_api_version": api_versions, "app_title": [app.replace("bwh_", "").title()]}
				for app, api_versions in api_versions_by_app.items()
			},
		)

	def write_manifest(
		self, entries: list, app: str = APP, api_version: int = API_VERSION, **manifest_fields
	):
		self.write_asset(
			app,
			"manifest.json",
			json.dumps(
				{"api_version": api_version, "kit_version": "0.2.0", "app": app, "entries": entries}
				| manifest_fields
			),
		)

	def write_asset(self, app: str, relative_path: str, content: str):
		path = os.path.join(self.assets_folder, app, relative_path)
		os.makedirs(os.path.dirname(path), exist_ok=True)
		with open(path, "w") as asset_file:
			asset_file.write(content)

	def entries_by_key(self) -> dict:
		return {entry["key"]: entry for entry in get_registry()["entries"]}


class TestPluginDiscovery(PluginTestCase):
	def test_only_apps_with_a_manifest_add_entries(self):
		self.write_manifest([page()])

		plugins = get_registry()

		self.assertEqual(plugins["apps"], {APP: {"title": "Shipping"}})
		self.assertEqual([entry["key"] for entry in plugins["entries"]], [f"{APP}:pages:jobs"])
		self.assertEqual(plugins["problems"], [])

	def test_a_malformed_manifest_is_logged_and_the_other_apps_survive(self):
		self.write_asset(OTHER_APP, "manifest.json", "{not json")
		self.write_manifest([page()])

		plugins = get_registry()

		self.assertEqual({entry["app"] for entry in plugins["entries"]}, {APP})
		self.assertEqual([problem["app"] for problem in plugins["problems"]], [OTHER_APP])
		self.assertTrue(error_logged(f"Commera plugin {OTHER_APP}:manifest.json skipped", self.started_at))

	def test_a_manifest_built_for_another_api_marks_every_plugin_failed(self):
		self.write_manifest([page(), action()], api_version=API_VERSION + 1)

		entries = get_registry()["entries"]

		self.assertEqual(len(entries), 2)
		for entry in entries:
			self.assertIn(f"Commera API {API_VERSION + 1}", entry["error"])
			self.assertIsNone(entry.get("module_url"))

	def test_an_app_that_does_not_support_this_commera_is_skipped(self):
		self.declare_apps({APP: [API_VERSION + 1]})
		self.write_manifest([page()])

		self.assertEqual(get_registry()["entries"], [])

	def test_a_module_reports_whether_it_is_built_for_this_api(self):
		self.write_manifest([page("jobs"), page("wrong-api"), page("no-banner"), page("missing"), action()])
		self.write_asset(
			APP, "pages/jobs.js", f"/* commera-plugin-api: {API_VERSION} */\nexport default {{}}"
		)
		self.write_asset(APP, "pages/wrong-api.js", "/* commera-plugin-api: 99 */\nexport default {}")
		self.write_asset(APP, "pages/no-banner.js", "import { ref } from 'vue'")

		entries = self.entries_by_key()

		self.assertEqual(
			entries[f"{APP}:pages:jobs"]["module_url"], f"/assets/{APP}/commera/pages/jobs.js?v=9f2c1a"
		)
		self.assertIsNone(entries[f"{APP}:pages:jobs"].get("error"))
		self.assertIn("API 99", entries[f"{APP}:pages:wrong-api"]["error"])
		self.assertIn("plugin-kit", entries[f"{APP}:pages:no-banner"]["error"])
		self.assertIn("isn't built", entries[f"{APP}:pages:missing"]["error"])
		self.assertIsNone(entries[f"{APP}:pages:missing"].get("module_url"))
		self.assertIsNone(entries[f"{APP}:order/actions:resend"].get("error"))

	def test_an_app_icon_reaches_the_boot_with_a_content_hash(self):
		icon = '<svg viewBox="0 0 24 24"><path d="M2 2h20v20H2z"/></svg>'
		self.write_manifest([page()], icon="icon.svg")
		self.write_asset(APP, "icon.svg", icon)
		self.write_manifest([page()], app=OTHER_APP, icon="icon.svg")

		visible = get_visible_plugins("Administrator")

		digest = hashlib.sha256(icon.encode()).hexdigest()[:8]
		self.assertEqual(visible["apps"][APP]["icon_url"], f"/assets/{APP}/commera/icon.svg?v={digest}")
		self.assertNotIn("icon_url", visible["apps"][OTHER_APP])
		with self.set_user(SYSTEM_MANAGER):
			icon_urls = {row["app"]: row["icon_url"] for row in get_plugins()}
		self.assertEqual(icon_urls[APP], visible["apps"][APP]["icon_url"])
		self.assertIsNone(icon_urls[OTHER_APP])

	def test_an_icon_outside_public_commera_is_ignored(self):
		self.write_asset(APP, "../icon.svg", "<svg/>")
		self.write_manifest([page()], icon="../icon.svg")

		self.assertNotIn("icon_url", get_registry()["apps"][APP])


class TestPluginValidation(PluginTestCase):
	def test_each_invalid_entry_is_dropped_logged_and_listed_as_a_problem(self):
		invalid_entries = {
			"unknown place": card(place="order/blocks"),
			"reserved place": card(place="orders/selection"),
			"bad slug": card(name="Print_Status"),
			"condition outside the app": card(condition="frappe.utils.now"),
			"condition that can't be imported": card(condition=f"{FUNCTIONS}.missing"),
			"method outside the app": action(method="frappe.client.delete"),
			"unwhitelisted method": action(method=f"{FUNCTIONS}.unlisted_method"),
			"requires a missing DocType": card(requires="No Such DocType"),
			"doctype that isn't a Single": app_settings(doctype="Sales Order"),
			"missing label": card(label=""),
			"action with a template and a method": action(module="order/actions/resend.js"),
			"action with neither": action(method=None),
			"settings with neither": app_settings(doctype=None),
			"page without a module": page(module=None),
			"module outside public/commera": page(module="../../secrets.js"),
			"icon outside the set": page(icon="lucide-printer"),
			"command with a module": command(module="commands/sync.js"),
			"command without a method": command(method=None),
			"command with an unwhitelisted method": command(method=f"{FUNCTIONS}.unlisted_method"),
		}
		for case, entry in invalid_entries.items():
			with self.subTest(case=case):
				started_at = now_datetime()
				self.write_manifest([page("kept"), entry])

				plugins = get_registry()

				self.assertEqual([entry["name"] for entry in plugins["entries"]], ["kept"])
				self.assertEqual(len(plugins["problems"]), 1)
				self.assertTrue(
					error_logged(f"Commera plugin {APP}:{entry['place']}/{entry['name']} skipped", started_at)
				)

	def test_a_duplicate_name_keeps_the_first_and_settings_is_one_per_app(self):
		self.write_manifest(
			[
				page(label="First"),
				page(label="Second"),
				app_settings(),
				app_settings(name="more-settings"),
				page(name="print-status", label="Same name, other place"),
				card(),
			]
		)

		plugins = get_registry()

		self.assertEqual(
			[(entry["place"], entry["name"], entry["label"]) for entry in plugins["entries"]],
			[
				("pages", "jobs", "First"),
				("settings", "settings", "Shipping"),
				("pages", "print-status", "Same name, other place"),
				("order/cards", "print-status", "Print status"),
			],
		)
		self.assertEqual(len(plugins["problems"]), 2)

	def test_the_grammar_names_the_three_records_commera_extends(self):
		self.assertEqual(RECORD_DOCTYPES, {"order": "Sales Order", "product": "Item", "customer": "Customer"})
		self.assertFalse(set(GRAMMAR["reserved"]) & set(PLACES))
		for place, spec in PLACES.items():
			with self.subTest(place=place):
				self.assertLessEqual(set(spec["required"]), set(spec["fields"]))


class TestPluginRegistryCache(PluginTestCase):
	@patch.dict(frappe.conf, {"developer_mode": 0})
	def test_outside_developer_mode_the_registry_is_cached_until_clear_cache(self):
		frappe.clear_cache()
		self.addCleanup(frappe.clear_cache)
		self.write_manifest([page()])
		self.assertEqual(len(get_registry()["entries"]), 1)

		self.write_manifest([page(), page("more")])
		self.assertEqual(len(get_registry()["entries"]), 1)

		frappe.clear_cache()
		self.assertEqual(len(get_registry()["entries"]), 2)

	def test_in_developer_mode_the_registry_is_rebuilt_every_time(self):
		self.write_manifest([page()])
		self.assertEqual(len(get_registry()["entries"]), 1)

		self.write_manifest([page(), page("more")])
		self.assertEqual(len(get_registry()["entries"]), 2)


class TestPluginVisibility(PluginTestCase):
	def visible_labels(self, user: str) -> list[str]:
		return sorted(entry["label"] for entry in get_visible_plugins(user)["entries"])

	def test_each_user_sees_only_the_plugins_whose_doctypes_they_can_read(self):
		self.write_manifest([page("stock", label="Stock", requires="Stock Entry")])
		self.write_manifest([page("quotes", label="Quotes", requires="Quotation")], app=OTHER_APP)

		self.assertEqual(self.visible_labels(STOCK_USER), ["Stock"])
		self.assertEqual(self.visible_labels(SALES_USER), ["Quotes"])
		self.assertEqual(self.visible_labels(SYSTEM_MANAGER), ["Quotes", "Stock"])
		self.assertEqual(list(get_visible_plugins(STOCK_USER)["apps"]), [APP])

	def test_a_page_condition_runs_at_boot_but_a_record_condition_waits_for_the_record(self):
		self.write_manifest(
			[
				page("shown", label="Shown", condition=f"{FUNCTIONS}.show_page"),
				page("hidden", label="Hidden", condition=f"{FUNCTIONS}.hide_page"),
				page("broken", label="Broken", condition=f"{FUNCTIONS}.raise_error"),
				card(label="Card", condition=f"{FUNCTIONS}.hide_record"),
			]
		)

		self.assertEqual(self.visible_labels(STOCK_USER), ["Card", "Shown"])
		self.assertTrue(error_logged(f"Commera plugin {APP}:pages:broken condition failed", self.started_at))

	def test_the_dashboard_boot_carries_no_server_paths(self):
		self.write_manifest(
			[
				page(condition=f"{FUNCTIONS}.show_page", requires="Stock Entry"),
				card(condition=f"{FUNCTIONS}.show_record"),
				action(),
			]
		)
		context = frappe._dict()
		with self.set_user(STOCK_USER), patch.object(frappe.db, "commit"):
			dashboard.get_context(context)

		plugins = context.boot.plugins
		self.assertEqual(plugins["apps"], {APP: {"title": "Shipping"}})
		self.assertEqual(
			[(entry["key"], entry["has_condition"], entry["has_method"]) for entry in plugins["entries"]],
			[
				(f"{APP}:pages:jobs", False, False),
				(f"{APP}:order/cards:print-status", True, False),
				(f"{APP}:order/actions:resend", False, True),
			],
		)
		self.assertEqual(
			set(plugins["entries"][0]),
			{
				"key",
				"app",
				"place",
				"name",
				"label",
				"icon",
				"keywords",
				"order",
				"sidebar",
				"doctype",
				"confirm",
			}
			| {"module_url", "error", "has_condition", "has_method"},
		)
		self.assertTrue(plugins["entries"][0]["sidebar"])
		self.assertNotIn(FUNCTIONS, json.dumps(plugins))


class TestRecordPlugins(PluginTestCase):
	def setUp(self):
		super().setUp()
		self.sales_order = make_test_sales_order(submit=False).name
		self.write_manifest(
			[
				card("shown", condition=f"{FUNCTIONS}.show_record"),
				card("hidden", condition=f"{FUNCTIONS}.hide_record"),
				card("broken", condition=f"{FUNCTIONS}.raise_error"),
				card("always"),
				card("listing", place="product/cards"),
				action("resend", condition=f"{FUNCTIONS}.show_record"),
				action("withheld", condition=f"{FUNCTIONS}.hide_record"),
				action("quotes-only", requires="Quotation"),
			]
		)

	def test_one_call_returns_every_card_and_action_whose_condition_passed(self):
		with self.set_user(STOCK_USER):
			keys = get_record_plugins("Sales Order", self.sales_order)["keys"]

		self.assertEqual(
			keys,
			[
				f"{APP}:order/cards:shown",
				f"{APP}:order/cards:always",
				f"{APP}:order/actions:resend",
			],
		)
		self.assertTrue(
			error_logged(f"Commera plugin {APP}:order/cards:broken condition failed", self.started_at)
		)

	def test_a_user_who_cannot_read_the_record_is_refused(self):
		with self.set_user(OUTSIDER), self.assertRaises(frappe.PermissionError):
			get_record_plugins("Sales Order", self.sales_order)

	def test_a_doctype_apps_cannot_extend_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			get_record_plugins("Quotation", self.sales_order)

	def test_running_an_action_returns_its_message(self):
		with self.set_user(STOCK_USER):
			response = run_record_action(f"{APP}:order/actions:resend", self.sales_order)

		self.assertEqual(response, {"message": f"Resent {self.sales_order}"})

	def test_running_an_action_rechecks_its_condition_and_requires(self):
		with self.set_user(STOCK_USER):
			for key in (f"{APP}:order/actions:withheld", f"{APP}:order/actions:quotes-only"):
				with self.subTest(key=key), self.assertRaises(frappe.PermissionError):
					run_record_action(key, self.sales_order)

		with self.set_user(SYSTEM_MANAGER):
			self.assertEqual(
				run_record_action(f"{APP}:order/actions:quotes-only", self.sales_order)["message"],
				f"Resent {self.sales_order}",
			)

	def test_a_card_or_unknown_key_cannot_be_run(self):
		for key in (f"{APP}:order/cards:shown", f"{APP}:order/actions:missing"):
			with self.subTest(key=key), self.assertRaises(frappe.DoesNotExistError):
				run_record_action(key, self.sales_order)


class TestCommands(PluginTestCase):
	def setUp(self):
		super().setUp()
		self.write_manifest(
			[
				command("sync"),
				command("quiet", label="Sync quietly", method=f"{FUNCTIONS}.sync_quietly"),
				command("hidden", label="Hidden", condition=f"{FUNCTIONS}.hide_page"),
				command("quotes-only", label="Quotes only", requires="Quotation"),
				action("resend"),
				page("jobs"),
			]
		)

	def test_the_boot_lists_only_commands_whose_condition_and_requires_pass(self):
		commands = {
			entry["name"]: entry
			for entry in get_visible_plugins(STOCK_USER)["entries"]
			if entry["place"] == "commands"
		}

		self.assertEqual(sorted(commands), ["quiet", "sync"])
		self.assertEqual(commands["sync"]["keywords"], ["printer"])
		self.assertTrue(commands["sync"]["has_method"])
		self.assertFalse(commands["sync"]["has_condition"])

	def test_running_a_command_returns_its_message_or_none(self):
		with self.set_user(STOCK_USER):
			self.assertEqual(run_command(f"{APP}:commands:sync"), {"message": "Synced 3 orders"})
			self.assertEqual(run_command(f"{APP}:commands:quiet"), {"message": None})

	def test_running_a_command_rechecks_its_condition_and_requires(self):
		with self.set_user(STOCK_USER):
			for key in (f"{APP}:commands:hidden", f"{APP}:commands:quotes-only"):
				with self.subTest(key=key), self.assertRaises(frappe.PermissionError):
					run_command(key)

		with self.set_user(SYSTEM_MANAGER):
			self.assertEqual(run_command(f"{APP}:commands:quotes-only")["message"], "Synced 3 orders")

	def test_only_a_command_runs_as_a_command_and_only_an_action_runs_on_a_record(self):
		for key in (f"{APP}:order/actions:resend", f"{APP}:pages:jobs", f"{APP}:commands:missing"):
			with self.subTest(key=key), self.assertRaises(frappe.DoesNotExistError):
				run_command(key)

		with self.assertRaises(frappe.DoesNotExistError):
			run_record_action(f"{APP}:commands:sync", make_test_sales_order(submit=False).name)


class TestPluginSettings(PluginTestCase):
	def setUp(self):
		super().setUp()
		self.write_manifest([app_settings()])
		self.addCleanup(frappe.clear_document_cache, SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)

	def test_reads_the_declared_single_as_field_groups_without_secrets(self):
		save_plugin_setting(APP, client_secret="secret-1")
		save_plugin_setting(APP, client_id="client-1")

		app_settings_data = get_plugin_settings(APP)

		self.assertEqual(app_settings_data["doctype"], SETTINGS_DOCTYPE)
		self.assertEqual(app_settings_data["values"]["client_id"], "client-1")
		self.assertIsNone(app_settings_data["values"]["client_secret"])
		fields = {
			field["fieldname"]: field for group in app_settings_data["groups"] for field in group["fields"]
		}
		self.assertTrue(fields["client_secret"]["is_set"])

	def test_a_blank_secret_keeps_the_stored_one(self):
		save_plugin_setting(APP, client_secret="secret-1")
		save_plugin_setting(APP, client_secret="")

		self.assertEqual(
			get_decrypted_password(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE, "client_secret"), "secret-1"
		)
		self.assertEqual(save_plugin_setting(APP, client_id="client-2"), {"client_id": "client-2"})

	def test_only_the_declared_single_is_reachable(self):
		with self.assertRaises(frappe.DoesNotExistError):
			get_plugin_settings(OTHER_APP)
		with self.assertRaises(frappe.ValidationError):
			save_plugin_setting(APP, no_such_field="value")

	def test_saving_needs_write_permission_on_the_single(self):
		with self.set_user(STOCK_USER), self.assertRaises(frappe.PermissionError):
			save_plugin_setting(APP, client_id="client-3")


class TestPluginSettingsWithRequiredFields(PluginTestCase):
	def setUp(self):
		super().setUp()
		self.write_manifest([app_settings(doctype=REQUIRED_SETTINGS_DOCTYPE)])
		self.addCleanup(frappe.clear_document_cache, REQUIRED_SETTINGS_DOCTYPE, REQUIRED_SETTINGS_DOCTYPE)
		for fieldname in ("sms_gateway_url", "message_parameter", "receiver_parameter"):
			frappe.db.set_single_value(REQUIRED_SETTINGS_DOCTYPE, fieldname, None)

	def test_a_row_saves_while_other_required_rows_are_blank(self):
		save_plugin_setting(APP, message_parameter="text")

		self.assertEqual(frappe.db.get_single_value(REQUIRED_SETTINGS_DOCTYPE, "message_parameter"), "text")
		self.assertFalse(frappe.db.get_single_value(REQUIRED_SETTINGS_DOCTYPE, "receiver_parameter"))

	def test_a_required_row_cannot_be_cleared(self):
		save_plugin_setting(APP, message_parameter="text")

		with self.assertRaises(frappe.MandatoryError):
			save_plugin_setting(APP, message_parameter="")
		self.assertEqual(frappe.db.get_single_value(REQUIRED_SETTINGS_DOCTYPE, "message_parameter"), "text")

	def test_the_single_still_runs_its_own_validation(self):
		with (
			patch.object(
				SMSSettings, "validate", side_effect=frappe.ValidationError("checked by the app"), create=True
			),
			self.assertRaisesRegex(frappe.ValidationError, "checked by the app"),
		):
			save_plugin_setting(APP, message_parameter="text")


class TestInstalledApps(PluginTestCase):
	def test_lists_each_plugin_with_its_entries_problems_and_failures(self):
		failed_before = self.get_installed_app(APP)["failed_deliveries"]
		sales_order = make_test_sales_order(submit=False).name
		make_order_event(
			sales_order,
			"order_placed",
			[
				{"app": APP, "handler": f"{APP}.placed", "status": "Failed", "attempts": 6},
				{"app": APP, "handler": f"{APP}.placed_again", "status": "Done", "attempts": 1},
			],
		)
		self.write_manifest([page(), card(place="order/blocks")])
		self.write_asset(APP, "pages/jobs.js", f"/* commera-plugin-api: {API_VERSION} */")

		installed_app = self.get_installed_app(APP)

		self.assertEqual(installed_app["title"], "Shipping")
		self.assertEqual(
			installed_app["entries"],
			[{"place": "pages", "name": "jobs", "label": "Print jobs", "error": None}],
		)
		self.assertEqual(len(installed_app["problems"]), 1)
		self.assertEqual(installed_app["failed_deliveries"], failed_before + 1)

	def test_deliveries_filter_by_status_and_page(self):
		sales_order = make_test_sales_order(submit=False).name
		make_order_event(
			sales_order,
			"order_placed",
			[
				{"app": "commera_test_app", "handler": "commera_test_app.one", "status": "Failed"},
				{"app": "commera_test_app", "handler": "commera_test_app.two", "status": "Failed"},
				{"app": "commera_test_app", "handler": "commera_test_app.three", "status": "Done"},
			],
		)

		with self.set_user(SYSTEM_MANAGER):
			failed = get_plugin_deliveries("commera_test_app", status="Failed", page_length=1)
			every_delivery = get_plugin_deliveries("commera_test_app")

		self.assertEqual(failed["total"], 2)
		self.assertEqual(
			[(row.status, row.reference_name) for row in failed["rows"]], [("Failed", sales_order)]
		)
		self.assertEqual(every_delivery["total"], 3)

	def test_only_a_system_manager_sees_installed_apps(self):
		with self.set_user(STOCK_USER):
			with self.assertRaises(frappe.PermissionError):
				get_plugins()
			with self.assertRaises(frappe.PermissionError):
				get_plugin_deliveries(APP)

	def get_installed_app(self, app: str) -> dict:
		with self.set_user(SYSTEM_MANAGER):
			return next(row for row in get_plugins() if row["app"] == app)
