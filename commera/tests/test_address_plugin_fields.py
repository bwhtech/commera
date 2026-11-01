# Copyright (c) 2026, company@bwhstudios.com and Contributors

"""Plugin fields on Address: the `<app>_...` fields an installed Commera plugin owns.

Checkout copies the ones its form sends, and the account SDK reads and writes them under `plugin_fields`, as the
cart and orders already do. With no plugin installed, saving an address behaves exactly as before.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.payments import add_party_address, get_party_address, get_plugin_address_values
from commera.sdk import account
from commera.sdk.types import CustomerAddress

PLUGIN_FIELD = "tata_shipping_location"

CHECKOUT_ADDRESS = {
	"city": "Riyadh",
	"country": "Saudi Arabia",
	"state": "Riyadh Province",
	"full_address": "1 Billing Street",
	"landmark": "Near the park",
	"po_box": "12345",
	"phone_number": "+966500000001",
	"email": "zz_extension@example.com",
	PLUGIN_FIELD: "LOCATION-1",
}

# What add_party_address built before plugin fields were copied.
TODAYS_VALUES = {
	"address_type": "Billing",
	"city": "Riyadh",
	"country": "Saudi Arabia",
	"state": "Riyadh Province",
	"address_line1": "1 Billing Street",
	"address_line2": "Near the park",
	"pincode": "12345",
	"phone": "+966500000001",
	"email_id": "zz_extension@example.com",
}


def plugin_fields(*fieldnames):
	return patch("commera.api.payments.get_plugin_fieldnames", return_value=list(fieldnames))


class TestCheckoutAddressPluginFields(IntegrationTestCase):
	def test_with_no_plugin_checkout_builds_exactly_todays_values(self):
		with (
			plugin_fields(),
			patch("commera.api.payments.get_party_address", return_value="EXISTING") as lookup,
			patch("commera.api.payments.frappe.get_doc") as get_doc,
		):
			add_party_address("Some Customer", CHECKOUT_ADDRESS, "Billing")

		lookup.assert_called_once_with("Some Customer", TODAYS_VALUES)
		get_doc.assert_called_once_with("Address", "EXISTING")

	def test_the_dedupe_filter_is_unchanged_with_no_plugin(self):
		with patch("commera.api.payments.frappe.get_all", return_value=[]) as get_all:
			get_party_address("Some Customer", dict(TODAYS_VALUES, address_line2=None))

		self.assertEqual(
			get_all.call_args.kwargs["filters"],
			[
				["Address", "address_type", "=", "Billing"],
				["Address", "city", "=", "Riyadh"],
				["Address", "country", "=", "Saudi Arabia"],
				["Address", "state", "=", "Riyadh Province"],
				["Address", "address_line1", "=", "1 Billing Street"],
				["Address", "address_line2", "is", "not set"],
				["Address", "pincode", "=", "12345"],
				["Address", "phone", "=", "+966500000001"],
				["Address", "email_id", "=", "zz_extension@example.com"],
				["Address", "disabled", "=", 0],
				["Dynamic Link", "link_doctype", "=", "Customer"],
				["Dynamic Link", "link_name", "=", "Some Customer"],
			],
		)

	def test_a_plugin_field_the_form_sends_is_saved_and_joins_the_dedupe(self):
		with (
			plugin_fields(PLUGIN_FIELD),
			patch("commera.api.payments.get_party_address", return_value="EXISTING") as lookup,
			patch("commera.api.payments.frappe.get_doc"),
		):
			add_party_address("Some Customer", CHECKOUT_ADDRESS, "Billing")

		self.assertEqual(lookup.call_args.args[1], {**TODAYS_VALUES, PLUGIN_FIELD: "LOCATION-1"})

	def test_a_plugin_field_the_form_does_not_send_is_left_out_and_an_empty_one_is_none(self):
		without = {key: value for key, value in CHECKOUT_ADDRESS.items() if key != PLUGIN_FIELD}
		with plugin_fields(PLUGIN_FIELD):
			self.assertEqual(get_plugin_address_values(without), {})
			self.assertEqual(get_plugin_address_values({**without, PLUGIN_FIELD: ""}), {PLUGIN_FIELD: None})

	def test_form_keys_no_plugin_owns_are_ignored(self):
		with plugin_fields(PLUGIN_FIELD):
			values = get_plugin_address_values({**CHECKOUT_ADDRESS, "owner": "x", "custom_note": "y"})

		self.assertEqual(values, {PLUGIN_FIELD: "LOCATION-1"})


class StoredAddress(dict):
	"""An Address stand-in: `name` plus dict-backed `get`, like a Document."""

	def __init__(self, name: str, **values):
		super().__init__(values)
		self.name = name


SDK_ADDRESS = {
	"address_line1": "1 Shopper Street",
	"city": "Bandung",
	"country": "Indonesia",
	"address_type": "Shipping",
}


class TestAccountSdkAddressPluginFields(IntegrationTestCase):
	"""The account SDK (account page and headless storefronts) reads and writes them under `plugin_fields`."""

	def owned(self, *fieldnames):
		"""Patch where both the SDK and `validate_plugin_fieldnames` look the plugin fields up."""
		for target in (
			"commera.sdk.account.get_plugin_fieldnames",
			"commera.plugin_events.get_plugin_fieldnames",
		):
			patcher = patch(target, return_value=list(fieldnames))
			patcher.start()
			self.addCleanup(patcher.stop)

	def add(self, address: dict, stored: StoredAddress):
		with (
			patch("commera.sdk.account.get_party", return_value=SimpleNamespace(name="Some Customer")),
			patch("commera.sdk.account.get_shopper", return_value="shopper@example.com"),
			patch("commera.sdk.account.get_profile", return_value={"full_name": "Some Shopper"}),
			patch("commera.sdk.account.add_customer_address", return_value=stored) as add_customer_address,
		):
			return account.save_address(address), add_customer_address

	def test_adding_an_address_saves_its_plugin_fields(self):
		self.owned(PLUGIN_FIELD)
		stored = StoredAddress("ADDR-1", **SDK_ADDRESS, **{PLUGIN_FIELD: "LOCATION-1"})

		result, add_customer_address = self.add(
			{**SDK_ADDRESS, "plugin_fields": {PLUGIN_FIELD: "LOCATION-1"}}, stored
		)

		self.assertEqual(add_customer_address.call_args.args[1][PLUGIN_FIELD], "LOCATION-1")
		self.assertEqual(result["plugin_fields"], {PLUGIN_FIELD: "LOCATION-1"})

	def test_a_field_no_installed_plugin_owns_is_refused(self):
		self.owned(PLUGIN_FIELD)
		with self.assertRaises(frappe.ValidationError):
			self.add({**SDK_ADDRESS, "plugin_fields": {"owner": "someone"}}, StoredAddress("ADDR-1"))

	def test_plugin_fields_must_be_an_object(self):
		self.owned(PLUGIN_FIELD)
		with self.assertRaises(frappe.ValidationError):
			self.add({**SDK_ADDRESS, "plugin_fields": ["LOCATION-1"]}, StoredAddress("ADDR-1"))

	def test_an_update_touches_only_the_fields_it_sends(self):
		self.owned(PLUGIN_FIELD)
		doc = MagicMock()
		doc.name = "ADDR-1"
		doc.get.return_value = None
		with patch("commera.sdk.account.get_own_address", return_value=doc):
			account.save_address({"name": "ADDR-1", "city": "Kollam"})
			account.save_address({"name": "ADDR-1", "plugin_fields": {PLUGIN_FIELD: "LOCATION-2"}})

		self.assertEqual(doc.update.call_args_list[0].args[0], {"city": "Kollam"})
		self.assertEqual(doc.update.call_args_list[1].args[0], {PLUGIN_FIELD: "LOCATION-2"})

	def test_with_no_plugin_the_result_has_empty_plugin_fields_and_the_documented_shape(self):
		self.owned()
		result = account.get_address_result(StoredAddress("ADDR-1", **SDK_ADDRESS))

		self.assertEqual(result["plugin_fields"], {})
		self.assertEqual(set(result), CustomerAddress.__required_keys__ | CustomerAddress.__optional_keys__)
