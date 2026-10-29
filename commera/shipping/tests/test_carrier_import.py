# Copyright (c) 2026, Build With Hussain and contributors
# For license information, please see license.txt

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.shipping.doctype.aftership_shipping_settings.aftership_shipping_settings import (
	AfterShipShippingSettings,
	alpha_3,
	build_delivery_option_choices,
	origin_can_ship_from,
)
from commera.shipping.doctype.shipping_service.shipping_service import (
	create_shipping_services,
)
from commera.shipping.doctype.shiprocket_shipping_settings.shiprocket_shipping_settings import (
	ShiprocketShippingSettings,
)

SETTINGS_DOCTYPE = "AfterShip Shipping Settings"

try:
	import pycountry
except ImportError:
	pycountry = None


def shipper_account(account_id, slug, description=None):
	return {"id": account_id, "slug": slug, "description": description}


def courier(slug, ship_from, service_types):
	return {
		"slug": slug,
		"ship_from": ship_from,
		"courier_service_types": [
			{"service_type": service_type, "service_name": name} for service_type, name in service_types
		],
	}


class TestBuildDeliveryOptionChoices(IntegrationTestCase):
	"""What the importer offers: one group per shipper account, filtered to couriers that can collect."""

	def test_account_is_grouped_with_its_couriers_services(self):
		choices = build_delivery_option_choices(
			[shipper_account("acc-1", "dhl", "DHL Sandbox")],
			[courier("dhl", "IND", [("dhl_express", "Express"), ("dhl_economy", "Economy")])],
			"IND",
		)

		self.assertEqual(len(choices), 1)
		self.assertEqual(choices[0]["carrier"], "dhl")
		self.assertEqual(choices[0]["description"], "DHL Sandbox")
		self.assertEqual(
			choices[0]["services"],
			[
				# The account id has to survive into the Service Code, because buying a label needs both it
				# and the service type.
				{"service_code": "acc-1|dhl_express", "service_name": "Express"},
				{"service_code": "acc-1|dhl_economy", "service_name": "Economy"},
			],
		)

	def test_two_accounts_stay_in_separate_groups(self):
		choices = build_delivery_option_choices(
			[shipper_account("acc-1", "dhl"), shipper_account("acc-2", "fedex")],
			[
				courier("dhl", "Global", [("dhl_express", "Express")]),
				courier("fedex", "Global", [("fedex_priority", "Priority")]),
			],
			"IND",
		)

		self.assertEqual([choice["carrier"] for choice in choices], ["dhl", "fedex"])
		self.assertEqual(choices[0]["services"][0]["service_code"], "acc-1|dhl_express")
		self.assertEqual(choices[1]["services"][0]["service_code"], "acc-2|fedex_priority")

	def test_account_without_a_matching_courier_is_dropped(self):
		choices = build_delivery_option_choices(
			[shipper_account("acc-1", "dhl")],
			[courier("fedex", "Global", [("fedex_priority", "Priority")])],
			"IND",
		)

		self.assertEqual(choices, [])

	def test_courier_with_no_service_types_is_dropped(self):
		"""Importing it would create an option with a service type nobody can book."""
		choices = build_delivery_option_choices(
			[shipper_account("acc-1", "dhl")], [courier("dhl", "Global", [])], "IND"
		)

		self.assertEqual(choices, [])


class TestOriginCanShipFrom(IntegrationTestCase):
	"""`ship_from` is one string in three spellings, and getting it wrong offers uncollectable services."""

	def test_global_covers_every_origin(self):
		self.assertTrue(origin_can_ship_from("Global", "IND"))
		self.assertTrue(origin_can_ship_from("global", "USA"))

	def test_single_code_matches_only_itself(self):
		self.assertTrue(origin_can_ship_from("IND", "IND"))
		self.assertFalse(origin_can_ship_from("IND", "USA"))

	def test_comma_list_matches_any_member(self):
		self.assertTrue(origin_can_ship_from("HKG,SGP,MYS", "SGP"))
		self.assertTrue(origin_can_ship_from(" hkg , sgp ", "SGP"))
		self.assertFalse(origin_can_ship_from("HKG,SGP,MYS", "IND"))

	def test_empty_ship_from_matches_nothing(self):
		"""A courier that names no origin cannot be shown to collect from ours."""
		for value in (None, "", "   "):
			self.assertFalse(origin_can_ship_from(value, "IND"))


class TestAlpha3(IntegrationTestCase):
	"""AfterShip only accepts alpha-3, and the site stores alpha-2 on Country."""

	def test_resolved_from_the_countrys_stored_alpha_2_code(self):
		self.assertEqual(frappe.db.get_value("Country", "India", "code"), "in")
		self.assertEqual(alpha_3("India"), "IND")

	@unittest.skipUnless(pycountry, "pycountry is an optional dependency of this app")
	def test_falls_back_to_the_country_name_when_the_code_is_missing(self):
		frappe.db.set_value("Country", "Iceland", "code", "")
		self.assertEqual(alpha_3("Iceland"), "ISL")

	def test_no_country_is_not_an_error(self):
		"""An address with no country is a validation problem for the caller, not a crash here."""
		self.assertIsNone(alpha_3(None))

	def test_unresolvable_country_throws(self):
		"""Kosovo has no assigned ISO code, so neither route resolves it. A quote must fail loudly rather
		than send AfterShip an origin it will reject."""
		self.assertRaises(frappe.ValidationError, alpha_3, "Kosovo")


class TestCreateShippingServices(IntegrationTestCase):
	# Frappe rolls a test run back per class, not per test, so every case here uses its own service codes
	# and titles; sharing them would make one test's inserts another's "already imported".

	def setUp(self):
		self.provider = create_test_provider_profile()

	def test_creates_one_service_per_selection(self):
		created = create_shipping_services(
			self.provider,
			[
				{
					"service_code": "acc-1|create_express",
					"service_name": "_Test Create Express",
					"carrier": "dhl",
				},
				{
					"service_code": "acc-1|create_economy",
					"service_name": "_Test Create Economy",
					"carrier": "dhl",
				},
			],
		)

		self.assertEqual(created, ["_Test Create Express", "_Test Create Economy"])
		service = frappe.get_doc("Shipping Service", "_Test Create Express")
		self.assertEqual(service.provider, self.provider)
		self.assertEqual(service.service_code, "acc-1|create_express")
		self.assertEqual(service.carrier, "dhl")
		self.assertTrue(service.enabled)

	def test_the_desk_button_sends_selections_as_a_json_string(self):
		selections = [
			{"service_code": "acc-1|json_express", "service_name": "_Test Json Express", "carrier": "dhl"}
		]

		created = create_shipping_services(self.provider, frappe.as_json(selections))

		self.assertEqual(created, ["_Test Json Express"])

	def test_default_rate_seeds_the_backup_charge(self):
		create_shipping_services(
			self.provider,
			[{"service_code": "acc-1|rate_express", "service_name": "_Test Rate Express", "carrier": "dhl"}],
			default_rate=250,
		)

		charge = frappe.db.get_value("Shipping Service", "_Test Rate Express", "backup_charge")
		self.assertEqual(charge, 250)

	def test_reimport_skips_what_is_already_there(self):
		"""Re-running the import after adding a carrier must add only the new rows, not duplicate the old."""
		selections = [
			{"service_code": "acc-1|redo_express", "service_name": "_Test Redo Express", "carrier": "dhl"}
		]
		create_shipping_services(self.provider, selections)

		created = create_shipping_services(
			self.provider,
			[
				*selections,
				{"service_code": "acc-2|redo_pri", "service_name": "_Test Redo Priority", "carrier": "fedex"},
			],
		)

		self.assertEqual(created, ["_Test Redo Priority"])
		self.assertEqual(frappe.db.count("Shipping Service", {"service_code": "acc-1|redo_express"}), 1)

	def test_clashing_service_names_are_suffixed_with_the_carrier(self):
		"""Title is the autoname, so two carriers selling "Express" would otherwise collide on insert."""
		created = create_shipping_services(
			self.provider,
			[
				{"service_code": "acc-1|clash_express", "service_name": "_Test Clash", "carrier": "dhl"},
				{"service_code": "acc-2|clash_express", "service_name": "_Test Clash", "carrier": "fedex"},
			],
		)

		self.assertEqual(created, ["_Test Clash", "_Test Clash (fedex)"])

	def test_empty_selection_throws(self):
		self.assertRaises(frappe.ValidationError, create_shipping_services, self.provider, [])


class TestGetServiceChoices(IntegrationTestCase):
	"""The whitelisted entry point, with the AfterShip HTTP layer stubbed out."""

	def setUp(self):
		self.provider = create_test_provider_profile()
		self.settings = frappe.get_single(SETTINGS_DOCTYPE)
		self.settings.pickup_address = create_test_address("India")
		self.settings.shipper_account_id = None

	def test_throws_without_an_api_key(self):
		with patch.object(AfterShipShippingSettings, "get_password", return_value=None):
			self.assertRaises(frappe.ValidationError, self.settings.get_service_choices)

	def test_throws_without_a_pickup_address(self):
		self.settings.pickup_address = None
		with patch.object(AfterShipShippingSettings, "get_password", return_value="test-key"):
			self.assertRaises(frappe.ValidationError, self.settings.get_service_choices)

	def test_returns_the_provider_and_the_in_scope_accounts(self):
		with self.stubbed_carrier_calls(
			accounts=[shipper_account("acc-1", "dhl", "DHL"), shipper_account("acc-2", "fedex", "FedEx")],
			couriers=[
				courier("dhl", "IND", [("dhl_express", "Express")]),
				# Collects only from Hong Kong, so it cannot serve an Indian pickup address.
				courier("fedex", "HKG", [("fedex_pri", "Priority")]),
			],
		):
			choices = self.settings.get_service_choices()

		self.assertEqual(choices["provider"], self.provider)
		self.assertEqual([account["carrier"] for account in choices["accounts"]], ["dhl"])

	def test_a_configured_shipper_account_narrows_the_import(self):
		"""Rates are only shopped against that account, so importing another one's services is dead weight."""
		self.settings.shipper_account_id = "acc-2"
		with self.stubbed_carrier_calls(
			accounts=[shipper_account("acc-1", "dhl", "DHL"), shipper_account("acc-2", "fedex", "FedEx")],
			couriers=[
				courier("dhl", "Global", [("dhl_express", "Express")]),
				courier("fedex", "Global", [("fedex_pri", "Priority")]),
			],
		):
			choices = self.settings.get_service_choices()

		self.assertEqual([account["carrier"] for account in choices["accounts"]], ["fedex"])

	def test_only_a_provider_that_implements_it_advertises_the_capability(self):
		"""The importer is offered off `supports()`, so Shiprocket must not appear to have a catalogue."""
		self.assertTrue(AfterShipShippingSettings.supports("service_choices"))
		self.assertFalse(ShiprocketShippingSettings.supports("service_choices"))

	def stubbed_carrier_calls(self, accounts, couriers):
		"""Neutralise only the outbound boundary: no AfterShip traffic; everything else is real."""
		return patch.multiple(
			AfterShipShippingSettings,
			get_password=lambda *args, **kwargs: "test-key",
			list_shipper_accounts=lambda self: accounts,
			list_couriers=lambda self: couriers,
		)


def create_test_provider_profile() -> str:
	name = "_Test AfterShip Profile"
	if not frappe.db.exists("Shipping Provider Profile", name):
		frappe.get_doc(
			{
				"doctype": "Shipping Provider Profile",
				"__newname": name,
				"provider_settings": SETTINGS_DOCTYPE,
				"enabled": 1,
			}
		).insert()
	return name


def create_test_address(country: str) -> str:
	address = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": "_Test Carrier Import Pickup",
			"address_type": "Shipping",
			"address_line1": "1 Test Road",
			"city": "Mumbai",
			"pincode": "400001",
			"country": country,
		}
	).insert()
	return address.name
