# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

"""The dashboard Delivery Options API: managing Shipping Services without opening Desk."""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin.delivery_options import (
	build_screen,
	delete_delivery_option,
	get_carrier_service_choices,
	get_delivery_options,
	get_link_options,
	import_carrier_services,
	save_delivery_option,
	toggle_delivery_option,
)

AFTERSHIP_SETTINGS = "AfterShip Shipping Settings"
SHIPROCKET_SETTINGS = "Shiprocket Shipping Settings"
AFTERSHIP_PROFILE = "_Test Delivery AfterShip"
SHIPROCKET_PROFILE = "_Test Delivery Shiprocket"

CONNECTOR_APP = "bwh_shipping"


def create_provider_profile(name: str, provider_settings: str, enabled: int = 1) -> str:
	if not frappe.db.exists("Shipping Provider Profile", name):
		frappe.get_doc(
			{
				"doctype": "Shipping Provider Profile",
				"__newname": name,
				"provider_settings": provider_settings,
				"enabled": enabled,
			}
		).insert()
	return name


def find_option(screen, title):
	return next((option for option in screen["options"] if option["title"] == title), None)


def field_names(screen):
	return [field["fieldname"] for group in screen["field_groups"] for field in group["fields"]]


@unittest.skipUnless(
	CONNECTOR_APP in frappe.get_installed_apps(), "delivery options need the shipping connector"
)
class TestAdminDeliveryOptions(IntegrationTestCase):
	# Frappe rolls a test run back per class, so each case uses its own titles; sharing them would make
	# one case's inserts another's pre-existing row.

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.clear_cache)

		frappe.set_user("Administrator")
		self.provider = create_provider_profile(AFTERSHIP_PROFILE, AFTERSHIP_SETTINGS)

	def create_option(self, title, **values):
		# A Shipping Service is enabled by default and refuses to be enabled without a service code,
		# so every fixture here carries one unless the case is about that rule.
		return save_delivery_option(
			values={
				"title": title,
				"provider": self.provider,
				"service_code": f"acc-1|{frappe.scrub(title)}",
				"backup_charge": 100,
				**values,
			}
		)

	def test_the_screen_names_the_picker_its_link_fields_search_through(self):
		# The provider is a required Link: without a picker the owner has to type a profile name exactly.
		self.assertEqual(get_delivery_options()["link_options_path"], "delivery_options.get_link_options")

	def test_the_picker_searches_a_doctype_the_option_actually_links_to(self):
		options = get_link_options("Shipping Provider Profile", search_text="_Test Delivery")

		self.assertIn(self.provider, [option["value"] for option in options])

	def test_the_picker_refuses_a_doctype_no_delivery_option_links_to(self):
		# Otherwise the whitelisted picker is a reader of any doctype the session can see.
		self.assertRaises(frappe.ValidationError, get_link_options, "User")

	def test_screen_lists_every_option_with_its_editor_layout(self):
		self.create_option("_Test List Express")

		screen = get_delivery_options()

		self.assertTrue(screen["available"])
		option = find_option(screen, "_Test List Express")
		self.assertEqual(option["provider"], self.provider)
		self.assertEqual(option["backup_charge"], 100)
		# The contract's whole option shape, so the screen never has to fetch a second time to edit one.
		self.assertEqual(
			set(option),
			{
				"name",
				"title",
				"description",
				"enabled",
				"provider",
				"service_code",
				"carrier",
				"markup_percent",
				"handling_fee",
				"backup_charge",
			},
		)

	def test_field_groups_come_from_the_doctypes_own_meta(self):
		screen = get_delivery_options()

		# Sectioned the way Desk sections it, so adding a docfield is all it takes to surface it.
		self.assertEqual([group["label"] for group in screen["field_groups"]], ["General", "Pricing"])
		self.assertIn("service_code", field_names(screen))
		self.assertIn("markup_percent", field_names(screen))

		provider_field = next(
			field
			for group in screen["field_groups"]
			for field in group["fields"]
			if field["fieldname"] == "provider"
		)
		self.assertEqual(provider_field["fieldtype"], "Link")
		self.assertEqual(provider_field["options"], "Shipping Provider Profile")
		self.assertFalse(provider_field["required"])

	def test_create_writes_a_shipping_service(self):
		screen = self.create_option("_Test Create Express", description="1-2 days", markup_percent=5)

		self.assertTrue(frappe.db.exists("Shipping Service", "_Test Create Express"))
		option = find_option(screen, "_Test Create Express")
		self.assertEqual(option["description"], "1-2 days")
		self.assertEqual(option["markup_percent"], 5)
		# The write answers with the whole screen, so the editor never renders a stale list.
		self.assertTrue(screen["available"])

	def test_edit_updates_the_option_it_names(self):
		self.create_option("_Test Edit Express")

		screen = save_delivery_option(
			name="_Test Edit Express",
			values={"description": "Next day", "handling_fee": 25},
		)

		option = find_option(screen, "_Test Edit Express")
		self.assertEqual(option["description"], "Next day")
		self.assertEqual(option["handling_fee"], 25)
		self.assertEqual(frappe.db.count("Shipping Service", {"title": "_Test Edit Express"}), 1)

	def test_enabled_options_are_listed_before_disabled_ones(self):
		self.create_option("_Test A Switched Off", enabled=0)
		screen = self.create_option("_Test Z Switched On")

		titles = [option["title"] for option in screen["options"]]
		self.assertLess(titles.index("_Test Z Switched On"), titles.index("_Test A Switched Off"))

	def test_clearing_the_provider_drops_the_carrier_service(self):
		self.create_option("_Test Own Delivery", carrier="Blue Dart")

		screen = save_delivery_option(name="_Test Own Delivery", values={"provider": ""})

		option = find_option(screen, "_Test Own Delivery")
		self.assertFalse(option["provider"])
		self.assertIsNone(option["service_code"])
		self.assertIsNone(option["carrier"])
		self.assertEqual(option["backup_charge"], 100)

	def test_edit_accepting_the_unchanged_title_is_not_a_rename(self):
		"""The editor posts back every field it rendered, title included."""
		self.create_option("_Test Same Title")

		screen = save_delivery_option(
			name="_Test Same Title", values={"title": "_Test Same Title", "handling_fee": 10}
		)

		self.assertEqual(find_option(screen, "_Test Same Title")["handling_fee"], 10)

	def test_edit_refuses_to_rename_an_option(self):
		"""Sales Order.custom_delivery_option stores the title, so a rename orphans placed orders."""
		self.create_option("_Test Rename Express")

		self.assertRaises(
			frappe.ValidationError,
			save_delivery_option,
			name="_Test Rename Express",
			values={"title": "_Test Renamed Express"},
		)
		self.assertTrue(frappe.db.exists("Shipping Service", "_Test Rename Express"))
		self.assertFalse(frappe.db.exists("Shipping Service", "_Test Renamed Express"))

	def test_save_refuses_a_fieldname_the_screen_does_not_render(self):
		self.assertRaises(
			frappe.ValidationError, save_delivery_option, values={"title": "_Test Bad", "owner": "x@y.com"}
		)

	def test_toggle_offers_and_withdraws_an_option(self):
		self.create_option("_Test Toggle Express")

		screen = toggle_delivery_option("_Test Toggle Express", 1)
		self.assertEqual(find_option(screen, "_Test Toggle Express")["enabled"], 1)

		screen = toggle_delivery_option("_Test Toggle Express", 0)
		self.assertEqual(find_option(screen, "_Test Toggle Express")["enabled"], 0)

	def test_toggle_runs_the_doctypes_own_validation(self):
		"""An option with no service code cannot be booked, so enabling it has to fail here."""
		self.create_option("_Test Toggle Unbookable", enabled=0, service_code="")

		self.assertRaises(frappe.ValidationError, toggle_delivery_option, "_Test Toggle Unbookable", 1)

	def test_delete_removes_the_option(self):
		self.create_option("_Test Delete Express")

		screen = delete_delivery_option("_Test Delete Express")

		self.assertIsNone(find_option(screen, "_Test Delete Express"))
		self.assertFalse(frappe.db.exists("Shipping Service", "_Test Delete Express"))

	def test_import_providers_lists_only_carriers_that_publish_a_catalogue(self):
		create_provider_profile(SHIPROCKET_PROFILE, SHIPROCKET_SETTINGS)

		providers = get_delivery_options()["import_providers"]

		names = [entry["provider"] for entry in providers]
		self.assertIn(AFTERSHIP_PROFILE, names)
		# Shiprocket picks the courier itself at booking time and has nothing to list.
		self.assertNotIn(SHIPROCKET_PROFILE, names)
		self.assertEqual(set(providers[0]), {"provider", "label"})

	def test_a_disabled_carrier_cannot_be_imported_from(self):
		frappe.db.set_value("Shipping Provider Profile", self.provider, "enabled", 0)
		frappe.clear_cache()

		self.assertRaises(frappe.ValidationError, get_carrier_service_choices, self.provider)

	def test_carrier_service_choices_come_from_the_providers_own_capability(self):
		with self.stubbed_carrier_calls():
			choices = get_carrier_service_choices(self.provider)

		self.assertEqual(choices["provider"], self.provider)
		self.assertEqual([account["carrier"] for account in choices["accounts"]], ["dhl"])

	def test_import_creates_one_option_per_selection_and_skips_a_repeat(self):
		selections = [
			{"service_code": "acc-1|imp_express", "service_name": "_Test Imp Express", "carrier": "dhl"}
		]

		screen = import_carrier_services(self.provider, selections, default_rate=250)

		option = find_option(screen, "_Test Imp Express")
		self.assertEqual(option["service_code"], "acc-1|imp_express")
		self.assertEqual(option["backup_charge"], 250)
		self.assertEqual(option["enabled"], 1)

		import_carrier_services(self.provider, selections)
		self.assertEqual(frappe.db.count("Shipping Service", {"service_code": "acc-1|imp_express"}), 1)

	def stubbed_carrier_calls(self):
		"""Neutralise only the outbound boundary — no AfterShip traffic, everything else is real."""
		from bwh_shipping.bwh_shipping.doctype.aftership_shipping_settings.aftership_shipping_settings import (
			AfterShipShippingSettings,
		)

		settings = frappe.get_single(AFTERSHIP_SETTINGS)
		settings.db_set("pickup_address", create_pickup_address(), update_modified=False)

		return patch.multiple(
			AfterShipShippingSettings,
			get_password=lambda *args, **kwargs: "test-key",
			list_shipper_accounts=lambda self: [{"id": "acc-1", "slug": "dhl", "description": "DHL"}],
			list_couriers=lambda self: [
				{
					"slug": "dhl",
					"ship_from": "IND",
					"courier_service_types": [{"service_type": "dhl_express", "service_name": "Express"}],
				}
			],
		)


class TestDeliveryOptionsWithoutTheConnector(IntegrationTestCase):
	"""bwh_shipping is a soft dependency: the screen degrades rather than breaking."""

	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		frappe.set_user("Administrator")

	def without_the_connector(self):
		# The real is_connector_installed() still runs; only the installed-app list it reads is narrowed,
		# so this exercises the same code path a site without bwh_shipping takes.
		installed = [app for app in frappe.get_installed_apps() if app != CONNECTOR_APP]
		return patch.object(frappe, "get_installed_apps", return_value=installed)

	def test_screen_reports_itself_unavailable_and_empty(self):
		with self.without_the_connector():
			screen = build_screen()

		self.assertEqual(
			screen,
			{
				"available": False,
				"options": [],
				"field_groups": [],
				"import_providers": [],
				"link_options_path": "",
			},
		)

	def test_a_write_refuses_rather_than_half_working(self):
		with self.without_the_connector():
			self.assertRaises(frappe.ValidationError, save_delivery_option, values={"title": "_Test Nope"})


def create_pickup_address() -> str:
	return (
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": "_Test Delivery Options Pickup",
				"address_type": "Shipping",
				"address_line1": "1 Test Road",
				"city": "Mumbai",
				"pincode": "400001",
				"country": "India",
			}
		)
		.insert()
		.name
	)
