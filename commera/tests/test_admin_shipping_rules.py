# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

"""The dashboard Shipping rates API: Shipping Rules and their bands, managed without opening Desk."""

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin.shipping_rules import (
	delete_shipping_rule,
	get_default_account,
	get_link_options,
	get_shipping_rule,
	get_shipping_rules,
	save_shipping_rule,
)
from commera.tests.test_admin_delivery_options import (
	AFTERSHIP_PROFILE,
	AFTERSHIP_SETTINGS,
	create_provider_profile,
)

CONNECTOR_APP = "bwh_shipping"

FREE_ABOVE_BANDS = [
	{"from_value": 0, "to_value": 999, "shipping_amount": 99},
	{"from_value": 999, "to_value": 0, "shipping_amount": 0},
]


@unittest.skipUnless(CONNECTOR_APP in frappe.get_installed_apps(), "pricing lives in the shipping connector")
class TestAdminShippingRules(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.clear_cache)
		frappe.set_user("Administrator")

		self.company = frappe.db.get_single_value("Commera Settings", "company")
		self.label = f"_Test Rate {frappe.generate_hash(length=6)}"

	def save_rule(self, bands=FREE_ABOVE_BANDS, **values):
		save_shipping_rule(label=self.label, bands=frappe.as_json(bands), **values)
		return get_shipping_rule(self.label)

	def assert_refused(self, bands, message_part):
		with self.assertRaises(frappe.ValidationError) as refusal:
			self.save_rule(bands)
		self.assertIn(message_part, str(refusal.exception))
		self.assertFalse(frappe.db.exists("Shipping Rule", self.label))

	def test_a_new_rule_takes_the_store_defaults(self):
		rule = self.save_rule()

		self.assertEqual(rule.company, self.company)
		self.assertEqual(rule.calculate_based_on, "Net Total")
		self.assertEqual(frappe.db.get_value("Shipping Rule", rule.name, "shipping_rule_type"), "Selling")
		self.assertEqual(rule.cost_center, frappe.get_cached_value("Company", self.company, "cost_center"))
		self.assertEqual(rule.account, get_default_account(self.company))

	def test_the_default_account_is_the_freight_account_not_any_chargeable_one(self):
		account = get_default_account(self.company)

		self.assertIsNotNone(account, "the test company's chart should carry a freight account")
		self.assertIn("freight", account.lower())

	def test_without_a_freight_account_the_owner_must_pick_one(self):
		frappe.db.set_value(
			"Account",
			{"company": self.company, "account_name": ("like", "%freight%")},
			"account_name",
			"Carriage Costs",
		)

		with self.assertRaises(frappe.ValidationError) as refusal:
			self.save_rule()
		self.assertIn("freight expense account", str(refusal.exception))

		chosen = frappe.db.get_value(
			"Account", {"company": self.company, "is_group": 0, "root_type": "Expense"}, "name"
		)
		self.assertEqual(self.save_rule(account=chosen).account, chosen)

	def test_bands_round_trip_lowest_first(self):
		self.save_rule(list(reversed(FREE_ABOVE_BANDS)))

		self.assertEqual(
			[
				(band.from_value, band.to_value, band.shipping_amount)
				for band in get_shipping_rule(self.label).bands
			],
			[(0, 999, 99), (999, 0, 0)],
		)

		save_shipping_rule(
			name=self.label,
			calculate_based_on="Net Weight",
			bands=[{"from_value": 0, "to_value": 5, "shipping_amount": 40}],
		)
		rule = get_shipping_rule(self.label)
		self.assertEqual(rule.calculate_based_on, "Net Weight")
		self.assertEqual([(band.from_value, band.to_value) for band in rule.bands], [(0, 5)])

	def test_the_screen_lists_the_rule_with_its_bands(self):
		self.save_rule()

		screen = get_shipping_rules()
		rule = next(rule for rule in screen["rules"] if rule["name"] == self.label)
		self.assertEqual(len(rule["bands"]), 2)
		self.assertEqual(rule["used_by"], [])
		self.assertEqual(screen["link_options_path"], "shipping_rules.get_link_options")

	def test_a_rule_needs_a_band(self):
		self.assert_refused([], "at least one price band")

	def test_a_negative_charge_is_refused(self):
		self.assert_refused([{"from_value": 0, "to_value": 100, "shipping_amount": -1}], "less than zero")

	def test_from_must_be_below_to(self):
		self.assert_refused(
			[{"from_value": 500, "to_value": 100, "shipping_amount": 10}], "less than to value"
		)

	def test_overlapping_bands_are_refused(self):
		self.assert_refused(
			[
				{"from_value": 0, "to_value": 500, "shipping_amount": 50},
				{"from_value": 400, "to_value": 900, "shipping_amount": 30},
			],
			"Bands overlap",
		)

	def test_only_the_top_band_may_be_open_ended(self):
		self.assert_refused(
			[
				{"from_value": 0, "to_value": 0, "shipping_amount": 0},
				{"from_value": 100, "to_value": 200, "shipping_amount": 30},
			],
			"highest band",
		)

	def test_weight_or_value_only(self):
		with self.assertRaises(frappe.ValidationError):
			self.save_rule(calculate_based_on="Fixed")

	def test_a_rule_a_delivery_option_prices_from_cannot_be_deleted(self):
		self.save_rule()
		option = frappe.get_doc(
			{
				"doctype": "Shipping Service",
				"title": f"_Test Rate Option {frappe.generate_hash(length=6)}",
				"enabled": 0,
				"provider": create_provider_profile(AFTERSHIP_PROFILE, AFTERSHIP_SETTINGS),
				"shipping_rule": self.label,
			}
		).insert()

		with self.assertRaises(frappe.LinkExistsError) as refusal:
			delete_shipping_rule(self.label)
		self.assertIn(option.title, str(refusal.exception))
		self.assertTrue(frappe.db.exists("Shipping Rule", self.label))

	def test_the_store_default_rule_cannot_be_deleted(self):
		self.save_rule()
		frappe.db.set_single_value("Commera Settings", "shipping_rule", self.label)

		with self.assertRaises(frappe.LinkExistsError) as refusal:
			delete_shipping_rule(self.label)
		self.assertIn("default shipping rule", str(refusal.exception))

	def test_an_unused_rule_is_deleted(self):
		self.save_rule()

		screen = delete_shipping_rule(self.label)

		self.assertFalse(frappe.db.exists("Shipping Rule", self.label))
		self.assertNotIn(self.label, [rule["name"] for rule in screen["rules"]])

	def test_pricing_picks_the_band_that_covers_the_cart(self):
		from bwh_shipping.bwh_shipping.pricing import get_covering_band

		self.save_rule()

		self.assertEqual(get_covering_band(self.label, {"base_net_total": 500}).shipping_amount, 99)
		self.assertEqual(get_covering_band(self.label, {"base_net_total": 999}).shipping_amount, 99)
		free_band = get_covering_band(self.label, {"base_net_total": 50000})
		self.assertEqual((free_band.shipping_amount, free_band.to_value), (0, 0))

	def test_a_weight_rule_brackets_on_weight_not_value(self):
		from bwh_shipping.bwh_shipping.pricing import get_covering_band

		self.save_rule(
			[
				{"from_value": 0, "to_value": 2, "shipping_amount": 40},
				{"from_value": 2, "to_value": 0, "shipping_amount": 90},
			],
			calculate_based_on="Net Weight",
		)

		band = get_covering_band(self.label, {"weight": 5, "base_net_total": 1})
		self.assertEqual(band.shipping_amount, 90)

	def test_pickers_cannot_search_outside_the_rule_links(self):
		with self.assertRaises(frappe.ValidationError):
			get_link_options("User")

		accounts = get_link_options("Account", "freight")
		self.assertTrue(accounts)
		self.assertTrue(
			all(
				account["value"].endswith(frappe.get_cached_value("Company", self.company, "abbr"))
				for account in accounts
			)
		)

	def test_only_a_system_manager_may_edit_rates(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_shipping_rules()
