# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

"""The dashboard Shipping Rules API: the store company's selling Shipping Rules and the one checkout uses."""

import unittest
from unittest.mock import patch

import frappe
from erpnext.accounts.doctype.shipping_rule.shipping_rule import (
	ManyBlankToValuesError,
	OverlappingConditionError,
)
from frappe.tests import IntegrationTestCase

from commera.api.admin.delivery_options import save_delivery_option
from commera.api.admin.shipping_rates import (
	delete_shipping_rule,
	get_shipping_rules,
	new_store_rule,
	save_shipping_rule,
	set_store_rule,
)
from commera.tests.test_admin_delivery_options import AFTERSHIP_SETTINGS, create_provider_profile

CONNECTOR_APP = "bwh_shipping"
PROVIDER_PROFILE = "_Test Rates AfterShip"
RULE_LABEL = "_Test Rates Rule"


def get_option_name(screen, title):
	return next(option["name"] for option in screen["delivery_options"] if option["title"] == title)


def get_rule(screen, name):
	return next(rule for rule in screen["rules"] if rule["name"] == name)


def get_band_ranges(rule):
	return [(band["from_value"], band["to_value"]) for band in rule["bands"]]


@unittest.skipUnless(
	CONNECTOR_APP in frappe.get_installed_apps(), "shipping rules need the shipping connector"
)
class TestAdminShippingRules(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		# Commera Settings is a Single: its cached copy outlives the rollback unless it is cleared too.
		self.addCleanup(frappe.clear_cache)
		self.addCleanup(frappe.db.rollback)
		frappe.set_user("Administrator")

		quotes = patch("bwh_shipping.bwh_shipping.pricing.get_live_quotes", return_value={})
		quotes.start()
		self.addCleanup(quotes.stop)

		# Every case starts from a store with no rule in use, so the demo's own rule is never edited.
		frappe.db.set_single_value("Commera Settings", "shipping_rule", None)

		provider = create_provider_profile(PROVIDER_PROFILE, AFTERSHIP_SETTINGS)
		for title in ("_Test Rates Standard", "_Test Rates Express"):
			save_delivery_option(
				values={
					"title": title,
					"provider": provider,
					"service_code": f"acc-1|{frappe.scrub(title)}",
					"backup_charge": 100,
				}
			)

		screen = get_shipping_rules()
		self.standard = get_option_name(screen, "_Test Rates Standard")
		self.express = get_option_name(screen, "_Test Rates Express")

	def create_rule(self, label=RULE_LABEL, conditions=None, use_at_checkout=0):
		save_shipping_rule(
			label=label,
			conditions=conditions or [{"from_value": 0, "to_value": 999, "shipping_amount": 99}],
			use_at_checkout=use_at_checkout,
		)
		return label

	def test_screen_lists_the_options_and_currency(self):
		screen = get_shipping_rules()

		self.assertTrue(screen["available"])
		self.assertIsNone(screen["store_rule"])
		company = frappe.db.get_single_value("Commera Settings", "company")
		self.assertEqual(screen["currency"], frappe.db.get_value("Company", company, "default_currency"))
		self.assertEqual(
			set(screen["delivery_options"][0]),
			{"name", "title", "description", "enabled", "provider", "service_code", "carrier"}
			| {"markup_percent", "handling_fee", "backup_charge"},
		)

	def test_create_makes_a_selling_order_value_rule_on_the_company_without_using_it(self):
		name = self.create_rule()

		rule = frappe.get_doc("Shipping Rule", name)
		company = frappe.db.get_single_value("Commera Settings", "company")
		self.assertEqual(rule.shipping_rule_type, "Selling")
		self.assertEqual(rule.calculate_based_on, "Net Total")
		self.assertEqual(rule.company, company)
		self.assertEqual(frappe.db.get_value("Account", rule.account, "company"), company)
		self.assertEqual(frappe.db.get_value("Cost Center", rule.cost_center, "company"), company)
		self.assertIsNone(frappe.db.get_single_value("Commera Settings", "shipping_rule"))
		self.assertEqual(get_band_ranges(get_rule(get_shipping_rules(), name)), [(0, 999)])

	def test_create_with_use_at_checkout_links_it_on_commera_settings(self):
		name = self.create_rule(use_at_checkout=1)

		self.assertEqual(frappe.db.get_single_value("Commera Settings", "shipping_rule"), name)
		self.assertEqual(get_shipping_rules()["store_rule"], name)

	def test_create_refuses_a_blank_name(self):
		with self.assertRaises(frappe.ValidationError):
			save_shipping_rule(label="  ", conditions=[])

	def test_edit_replaces_the_conditions_with_their_delivery_options(self):
		name = self.create_rule()

		screen = save_shipping_rule(
			name=name,
			conditions=[
				{"from_value": 0, "to_value": 499, "shipping_amount": 50, "shipping_service": self.standard},
				{"from_value": 500, "to_value": 0, "shipping_amount": 0, "shipping_service": self.express},
			],
		)

		rule = get_rule(screen, name)
		self.assertEqual(get_band_ranges(rule), [(0, 499), (500, 0)])
		self.assertEqual([band["shipping_service"] for band in rule["bands"]], [self.standard, self.express])

	def test_edit_forces_order_value(self):
		rule = new_store_rule("_Test Rates Weight Rule")
		rule.calculate_based_on = "Net Weight"
		rule.append("conditions", {"from_value": 0, "to_value": 2, "shipping_amount": 10})
		rule.insert()

		save_shipping_rule(
			name=rule.name, conditions=[{"from_value": 0, "to_value": 2, "shipping_amount": 10}]
		)

		self.assertEqual(frappe.db.get_value("Shipping Rule", rule.name, "calculate_based_on"), "Net Total")

	def test_edit_refuses_a_new_label(self):
		name = self.create_rule()

		with self.assertRaises(frappe.ValidationError):
			save_shipping_rule(name=name, label="Renamed", conditions=[])

	def test_a_free_band_saves_no_amount(self):
		# ERPNext's own fallback applies the store rule as a tax row and ignores free_shipping.
		name = self.create_rule(
			conditions=[{"from_value": 999, "to_value": 0, "shipping_amount": 99, "free_shipping": 1}]
		)

		(band,) = get_rule(get_shipping_rules(), name)["bands"]
		self.assertEqual(band["shipping_amount"], 0)
		self.assertEqual(band["free_shipping"], 1)

	def test_an_unknown_delivery_option_is_refused(self):
		with self.assertRaises(frappe.DoesNotExistError):
			self.create_rule(
				conditions=[
					{"from_value": 0, "to_value": 0, "shipping_amount": 9, "shipping_service": "nope"}
				]
			)

	def test_overlapping_bands_are_refused_across_delivery_options(self):
		with self.assertRaises(OverlappingConditionError):
			self.create_rule(
				conditions=[
					{
						"from_value": 0,
						"to_value": 999,
						"shipping_amount": 99,
						"shipping_service": self.standard,
					},
					{
						"from_value": 500,
						"to_value": 2000,
						"shipping_amount": 199,
						"shipping_service": self.express,
					},
				]
			)

	def test_a_second_open_ended_band_is_refused(self):
		with self.assertRaises(ManyBlankToValuesError):
			self.create_rule(
				conditions=[
					{"from_value": 999, "to_value": 0, "shipping_amount": 0},
					{"from_value": 5000, "to_value": 0, "shipping_amount": 199},
				]
			)

	def test_set_store_rule_switches_the_rule_checkout_uses(self):
		first = self.create_rule(use_at_checkout=1)
		second = self.create_rule(label="_Test Rates Rule Two")

		screen = set_store_rule(second)

		self.assertEqual(screen["store_rule"], second)
		self.assertNotEqual(screen["store_rule"], first)
		self.assertEqual(frappe.db.get_single_value("Commera Settings", "shipping_rule"), second)

	def test_set_store_rule_refuses_another_companys_rule(self):
		store_company = frappe.db.get_single_value("Commera Settings", "company")
		other_company = frappe.db.get_value("Company", {"name": ["!=", store_company]}, "name")
		if not other_company:
			self.skipTest("needs a second company")

		rule = new_store_rule("_Test Rates Other Company")
		rule.company = other_company
		rule.account = frappe.db.get_value("Account", {"company": other_company, "is_group": 0}, "name")
		rule.cost_center = frappe.db.get_value(
			"Cost Center", {"company": other_company, "is_group": 0}, "name"
		)
		rule.insert()

		with self.assertRaises(frappe.ValidationError):
			set_store_rule(rule.name)
		self.assertIsNone(frappe.db.get_single_value("Commera Settings", "shipping_rule"))

	def test_delete_is_refused_while_checkout_uses_the_rule(self):
		name = self.create_rule(use_at_checkout=1)

		with self.assertRaises(frappe.ValidationError):
			delete_shipping_rule(name)
		self.assertTrue(frappe.db.exists("Shipping Rule", name))

	def test_delete_removes_a_rule_checkout_does_not_use(self):
		name = self.create_rule()

		screen = delete_shipping_rule(name)

		self.assertFalse(frappe.db.exists("Shipping Rule", name))
		self.assertNotIn(name, [rule["name"] for rule in screen["rules"]])

	def test_a_non_system_manager_is_refused(self):
		name = self.create_rule()
		frappe.set_user("Guest")

		for call in (
			get_shipping_rules,
			lambda: save_shipping_rule(name=name, conditions=[]),
			lambda: delete_shipping_rule(name),
			lambda: set_store_rule(name),
		):
			with self.assertRaises(frappe.PermissionError):
				call()
