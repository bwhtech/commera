# Copyright (c) 2026, company@bwhstudios.com and Contributors
# The patch that moves each delivery option's own Shipping Rule onto the store rule's bands.

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from commera.patches.move_service_shipping_rules_to_store_rule import (
	move_service_shipping_rules_to_store_rule,
)
from commera.tests.test_delivery_option_charges import make_service, make_store_rule, set_store_rule

COMPANY = "Lifestyle Demo"


def set_legacy_rule(service: str | None, shipping_rule: str | None):
	"""Write the column the Shipping Service doctype no longer declares; None clears every service."""
	table = frappe.qb.DocType("Shipping Service")
	query = frappe.qb.update(table).set(table.shipping_rule, shipping_rule)
	if service:
		query = query.where(table.name == service)
	query.run()


def get_band_services(shipping_rule: str) -> list:
	return [band.shipping_service for band in frappe.get_doc("Shipping Rule", shipping_rule).conditions]


def count_error_logs() -> int:
	return frappe.db.count("Error Log")


class TestMoveServiceShippingRules(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.has_column("Shipping Service", "shipping_rule"):
			raise unittest.SkipTest("This site never had the per-option Shipping Rule column.")

		self.addCleanup(set_store_rule, frappe.db.get_single_value("Commera Settings", "shipping_rule"))
		# The demo site's real options carry legacy rules too; clear them so only this test's state moves.
		set_legacy_rule(None, None)

		suffix = frappe.generate_hash(length=6)
		self.standard = make_service(f"_Test Move Standard {suffix}")
		self.express = make_service(f"_Test Move Express {suffix}")
		self.store_rule = make_store_rule(
			[{"from_value": 0, "to_value": 100, "shipping_amount": 50}, {"from_value": 100, "to_value": 500}]
		).name

	def make_other_rule(self, bands: list[dict]) -> str:
		rule = make_store_rule(bands).name
		set_store_rule(self.store_rule)
		return rule

	def test_the_store_rule_bands_are_stamped_with_its_only_option(self):
		set_legacy_rule(self.standard, self.store_rule)

		move_service_shipping_rules_to_store_rule()

		self.assertEqual(get_band_services(self.store_rule), [self.standard, self.standard])

	def test_an_empty_store_rule_is_set_when_every_option_shares_one_rule(self):
		set_legacy_rule(self.standard, self.store_rule)
		set_store_rule(None)

		move_service_shipping_rules_to_store_rule()

		self.assertEqual(frappe.db.get_single_value("Commera Settings", "shipping_rule"), self.store_rule)
		self.assertEqual(get_band_services(self.store_rule), [self.standard, self.standard])

	def test_a_store_rule_shared_by_two_options_is_left_alone_and_logged(self):
		set_legacy_rule(self.standard, self.store_rule)
		set_legacy_rule(self.express, self.store_rule)
		error_logs = count_error_logs()

		move_service_shipping_rules_to_store_rule()

		self.assertEqual(get_band_services(self.store_rule), [None, None])
		self.assertEqual(count_error_logs(), error_logs + 1)

	def test_another_rule_is_merged_into_the_store_rule(self):
		other_rule = self.make_other_rule([{"from_value": 500, "to_value": 0, "shipping_amount": 20}])
		set_legacy_rule(self.express, other_rule)

		move_service_shipping_rules_to_store_rule()

		bands = frappe.get_doc("Shipping Rule", self.store_rule).conditions
		self.assertEqual(len(bands), 3)
		self.assertEqual(
			(bands[2].from_value, bands[2].to_value, bands[2].shipping_amount, bands[2].shipping_service),
			(500, 0, 20, self.express),
		)

	def test_another_rule_that_overlaps_the_store_rule_is_skipped_and_logged(self):
		other_rule = self.make_other_rule([{"from_value": 0, "to_value": 50, "shipping_amount": 20}])
		set_legacy_rule(self.express, other_rule)
		error_logs = count_error_logs()

		move_service_shipping_rules_to_store_rule()

		self.assertEqual(get_band_services(self.store_rule), [None, None])
		self.assertEqual(count_error_logs(), error_logs + 1)

	def test_running_twice_changes_nothing(self):
		other_rule = self.make_other_rule([{"from_value": 500, "to_value": 0, "shipping_amount": 20}])
		set_legacy_rule(self.standard, self.store_rule)
		set_legacy_rule(self.express, other_rule)

		move_service_shipping_rules_to_store_rule()
		first_run = frappe.get_doc("Shipping Rule", self.store_rule)
		move_service_shipping_rules_to_store_rule()
		second_run = frappe.get_doc("Shipping Rule", self.store_rule)

		self.assertEqual(second_run.modified, first_run.modified)
		self.assertEqual(
			get_band_services(self.store_rule), [self.standard, self.standard, self.express]
		)
