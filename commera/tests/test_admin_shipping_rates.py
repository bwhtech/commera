# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

"""The dashboard Shipping Rates API: the store Shipping Rule's bands, edited per delivery option."""

import unittest
from unittest.mock import patch

import frappe
from erpnext.accounts.doctype.shipping_rule.shipping_rule import (
	ManyBlankToValuesError,
	OverlappingConditionError,
)
from frappe.tests import IntegrationTestCase

from commera.api.admin.delivery_options import save_delivery_option
from commera.api.admin.shipping_rates import get_shipping_rates, save_service_rates, set_rate_basis
from commera.tests.test_admin_delivery_options import AFTERSHIP_SETTINGS, create_provider_profile

CONNECTOR_APP = "bwh_shipping"
PROVIDER_PROFILE = "_Test Rates AfterShip"


def get_option_name(screen, title):
	return next(option["name"] for option in screen["delivery_options"] if option["title"] == title)


def get_bands(screen, shipping_service):
	return [band for band in screen["bands"] if band["shipping_service"] == shipping_service]


@unittest.skipUnless(
	CONNECTOR_APP in frappe.get_installed_apps(), "shipping rates need the shipping connector"
)
class TestAdminShippingRates(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		# Commera Settings is a Single: its cached copy outlives the rollback unless it is cleared too.
		self.addCleanup(frappe.clear_cache)
		self.addCleanup(frappe.db.rollback)
		frappe.set_user("Administrator")

		quotes = patch("bwh_shipping.bwh_shipping.pricing.get_live_quotes", return_value={})
		quotes.start()
		self.addCleanup(quotes.stop)

		# Every case starts from a store with no rule, so the demo's own rule is never edited.
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

		screen = get_shipping_rates()
		self.standard = get_option_name(screen, "_Test Rates Standard")
		self.express = get_option_name(screen, "_Test Rates Express")

	def test_screen_lists_the_options_and_no_rule_before_the_first_save(self):
		screen = get_shipping_rates()

		self.assertTrue(screen["available"])
		self.assertIsNone(screen["rule"])
		self.assertEqual(screen["bands"], [])
		self.assertEqual(screen["calculate_based_on"], "Net Total")
		company = frappe.db.get_single_value("Commera Settings", "company")
		self.assertEqual(screen["currency"], frappe.db.get_value("Company", company, "default_currency"))
		self.assertEqual(
			set(screen["delivery_options"][0]),
			{"name", "title", "description", "enabled", "provider", "service_code", "carrier"}
			| {"markup_percent", "handling_fee", "backup_charge"},
		)

	def test_first_save_creates_a_selling_rule_on_the_company_and_links_it(self):
		screen = save_service_rates(
			self.standard, [{"from_value": 0, "to_value": 999, "shipping_amount": 99}]
		)

		rule = frappe.get_doc("Shipping Rule", screen["rule"])
		company = frappe.db.get_single_value("Commera Settings", "company")
		self.assertEqual(rule.shipping_rule_type, "Selling")
		self.assertEqual(rule.company, company)
		self.assertEqual(frappe.db.get_value("Account", rule.account, "company"), company)
		self.assertEqual(frappe.db.get_value("Cost Center", rule.cost_center, "company"), company)
		self.assertEqual(frappe.db.get_single_value("Commera Settings", "shipping_rule"), rule.name)

	def test_saving_one_option_leaves_the_others_bands_alone(self):
		save_service_rates(self.express, [{"from_value": 1000, "to_value": 5000, "shipping_amount": 199}])
		save_service_rates(self.standard, [{"from_value": 0, "to_value": 500, "shipping_amount": 50}])

		screen = save_service_rates(
			self.standard,
			[
				{"from_value": 0, "to_value": 999, "shipping_amount": 99},
				{"from_value": 5000, "to_value": 0, "shipping_amount": 0},
			],
		)

		standard = get_bands(screen, self.standard)
		self.assertEqual([(band["from_value"], band["to_value"]) for band in standard], [(0, 999), (5000, 0)])
		express = get_bands(screen, self.express)
		self.assertEqual([(band["from_value"], band["shipping_amount"]) for band in express], [(1000, 199)])

	def test_bands_naming_no_option_are_edited_as_their_own_group(self):
		save_service_rates(self.standard, [{"from_value": 0, "to_value": 999, "shipping_amount": 99}])
		screen = save_service_rates("", [{"from_value": 1000, "to_value": 2000, "shipping_amount": 10}])

		self.assertEqual(len(get_bands(screen, None)), 1)
		self.assertEqual(len(get_bands(screen, self.standard)), 1)

	def test_a_free_band_saves_no_amount(self):
		# ERPNext's own fallback applies the store rule as a tax row and ignores free_shipping.
		screen = save_service_rates(
			self.standard, [{"from_value": 999, "to_value": 0, "shipping_amount": 99, "free_shipping": 1}]
		)

		(band,) = get_bands(screen, self.standard)
		self.assertEqual(band["shipping_amount"], 0)
		self.assertEqual(band["free_shipping"], 1)

	def test_a_band_overlapping_another_options_band_is_refused(self):
		save_service_rates(self.standard, [{"from_value": 0, "to_value": 999, "shipping_amount": 99}])

		with self.assertRaises(OverlappingConditionError):
			save_service_rates(self.express, [{"from_value": 500, "to_value": 2000, "shipping_amount": 199}])

	def test_a_second_open_ended_band_is_refused(self):
		save_service_rates(self.standard, [{"from_value": 999, "to_value": 0, "shipping_amount": 0}])

		with self.assertRaises(ManyBlankToValuesError):
			save_service_rates(self.express, [{"from_value": 5000, "to_value": 0, "shipping_amount": 199}])

	def test_rate_basis_switches_between_value_and_weight_and_keeps_the_numbers(self):
		save_service_rates(self.standard, [{"from_value": 0, "to_value": 2, "shipping_amount": 99}])

		screen = set_rate_basis("Net Weight")

		self.assertEqual(screen["calculate_based_on"], "Net Weight")
		self.assertEqual([band["to_value"] for band in get_bands(screen, self.standard)], [2])
		self.assertEqual(set_rate_basis("Net Total")["calculate_based_on"], "Net Total")

	def test_rate_basis_refuses_fixed(self):
		# ShippingRule.validate deletes every band of a Fixed rule.
		save_service_rates(self.standard, [{"from_value": 0, "to_value": 999, "shipping_amount": 99}])

		with self.assertRaises(frappe.ValidationError):
			set_rate_basis("Fixed")

		self.assertEqual(len(get_bands(get_shipping_rates(), self.standard)), 1)

	def test_a_non_system_manager_is_refused(self):
		frappe.set_user("Guest")

		for call in (
			get_shipping_rates,
			lambda: save_service_rates(self.standard, []),
			lambda: set_rate_basis("Net Weight"),
		):
			with self.assertRaises(frappe.PermissionError):
				call()
