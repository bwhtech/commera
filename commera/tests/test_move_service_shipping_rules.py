# Copyright (c) 2026, company@bwhstudios.com and Contributors

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.patches.move_service_shipping_rules_to_store_rule import (
	NOT_MOVED_TITLE,
	get_legacy_service_rules,
	move_service_shipping_rules_to_store_rule,
)
from commera.tests.test_delivery_option_charges import make_service, make_store_rule, set_store_rule


def get_band_services(shipping_rule: str) -> list:
	return [band.shipping_service for band in frappe.get_doc("Shipping Rule", shipping_rule).conditions]


class TestMoveServiceShippingRules(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(set_store_rule, frappe.db.get_single_value("Commera Settings", "shipping_rule"))

		suffix = frappe.generate_hash(length=6)
		self.standard = make_service(f"_Test Move Standard {suffix}")
		self.express = make_service(f"_Test Move Express {suffix}")
		self.store_rule = make_store_rule(
			[{"from_value": 0, "to_value": 100, "shipping_amount": 50}, {"from_value": 100, "to_value": 500}]
		).name
		# Error Log rows outlive the test rollback, so the logs are captured rather than written.
		self.log_error = self.enterContext(patch.object(frappe, "log_error"))

	def make_other_rule(self, bands: list[dict]) -> str:
		rule = make_store_rule(bands).name
		set_store_rule(self.store_rule)
		return rule

	def count_logged(self, title: str = NOT_MOVED_TITLE) -> int:
		return sum(1 for call in self.log_error.call_args_list if call.kwargs.get("title") == title)

	def assert_logged(self):
		self.assertEqual(self.count_logged(), 1)

	def test_the_store_rule_bands_are_stamped_with_its_only_option(self):
		move_service_shipping_rules_to_store_rule({self.standard: self.store_rule})

		self.assertEqual(get_band_services(self.store_rule), [self.standard, self.standard])

	def test_a_store_rule_shared_by_two_options_is_left_alone_and_logged(self):
		move_service_shipping_rules_to_store_rule(
			{self.standard: self.store_rule, self.express: self.store_rule}
		)

		self.assertEqual(get_band_services(self.store_rule), [None, None])
		self.assertEqual(self.count_logged("Store Shipping Rule bands not assigned"), 1)

	def test_another_rule_is_merged_into_the_store_rule(self):
		other_rule = self.make_other_rule([{"from_value": 500, "to_value": 0, "shipping_amount": 20}])

		move_service_shipping_rules_to_store_rule({self.express: other_rule})

		bands = frappe.get_doc("Shipping Rule", self.store_rule).conditions
		self.assertEqual(len(bands), 3)
		self.assertEqual(
			(bands[2].from_value, bands[2].to_value, bands[2].shipping_amount, bands[2].shipping_service),
			(500, 0, 20, self.express),
		)

	def test_another_rule_that_overlaps_the_store_rule_is_rolled_back_and_logged(self):
		other_rule = self.make_other_rule([{"from_value": 0, "to_value": 50, "shipping_amount": 20}])

		move_service_shipping_rules_to_store_rule({self.express: other_rule})

		self.assertEqual(get_band_services(self.store_rule), [None, None])
		self.assertEqual(frappe.db.count("Shipping Rule Condition", {"parent": self.store_rule}), 2)
		self.assert_logged()

	def test_a_disabled_rule_is_skipped_and_logged(self):
		other_rule = self.make_other_rule([{"from_value": 500, "to_value": 0, "shipping_amount": 20}])
		frappe.db.set_value("Shipping Rule", other_rule, "disabled", 1)

		move_service_shipping_rules_to_store_rule({self.express: other_rule})

		self.assertEqual(get_band_services(self.store_rule), [None, None])
		self.assert_logged()

	def test_a_disabled_store_rule_is_not_stamped(self):
		frappe.db.set_value("Shipping Rule", self.store_rule, "disabled", 1)

		move_service_shipping_rules_to_store_rule({self.standard: self.store_rule})

		self.assertEqual(get_band_services(self.store_rule), [None, None])
		self.assert_logged()

	def test_without_a_store_rule_nothing_moves_and_the_setting_stays_empty(self):
		set_store_rule(None)

		move_service_shipping_rules_to_store_rule({self.standard: self.store_rule})

		self.assertFalse(frappe.db.get_single_value("Commera Settings", "shipping_rule"))
		self.assertEqual(get_band_services(self.store_rule), [None, None])
		self.assert_logged()

	def test_a_rule_without_bands_is_logged(self):
		other_rule = self.make_other_rule([{"from_value": 500, "to_value": 0, "shipping_amount": 20}])
		frappe.db.delete("Shipping Rule Condition", {"parent": other_rule})

		move_service_shipping_rules_to_store_rule({self.express: other_rule})

		self.assertEqual(get_band_services(self.store_rule), [None, None])
		self.assert_logged()

	def test_a_fixed_rule_is_logged(self):
		other_rule = self.make_other_rule([{"from_value": 500, "to_value": 0, "shipping_amount": 20}])
		frappe.db.set_value("Shipping Rule", other_rule, "calculate_based_on", "Fixed")

		move_service_shipping_rules_to_store_rule({self.express: other_rule})

		self.assertEqual(get_band_services(self.store_rule), [None, None])
		self.assert_logged()

	def test_a_rule_on_another_basis_is_logged(self):
		other_rule = self.make_other_rule([{"from_value": 500, "to_value": 0, "shipping_amount": 20}])
		frappe.db.set_value("Shipping Rule", other_rule, "calculate_based_on", "Net Weight")

		move_service_shipping_rules_to_store_rule({self.express: other_rule})

		self.assertEqual(get_band_services(self.store_rule), [None, None])
		self.assert_logged()

	def test_a_rule_of_another_company_is_logged(self):
		other_rule = self.make_other_rule([{"from_value": 500, "to_value": 0, "shipping_amount": 20}])
		frappe.db.set_value("Shipping Rule", other_rule, "company", "_Test Other Company")

		move_service_shipping_rules_to_store_rule({self.express: other_rule})

		self.assertEqual(get_band_services(self.store_rule), [None, None])
		self.assert_logged()

	def test_running_twice_changes_nothing(self):
		other_rule = self.make_other_rule([{"from_value": 500, "to_value": 0, "shipping_amount": 20}])
		legacy_rules = {self.standard: self.store_rule, self.express: other_rule}

		move_service_shipping_rules_to_store_rule(legacy_rules)
		first_run = frappe.get_doc("Shipping Rule", self.store_rule)
		move_service_shipping_rules_to_store_rule(legacy_rules)
		second_run = frappe.get_doc("Shipping Rule", self.store_rule)

		self.assertEqual(second_run.modified, first_run.modified)
		self.assertEqual(get_band_services(self.store_rule), [self.standard, self.standard, self.express])


class TestLegacyServiceRules(IntegrationTestCase):
	def test_each_option_is_read_with_its_legacy_rule(self):
		if not frappe.db.has_column("Shipping Service", "shipping_rule"):
			raise unittest.SkipTest("This site never had the per-option Shipping Rule column.")
		self.addCleanup(set_store_rule, frappe.db.get_single_value("Commera Settings", "shipping_rule"))
		service = make_service(f"_Test Legacy Option {frappe.generate_hash(length=6)}")
		shipping_rule = make_store_rule([{"from_value": 0, "to_value": 0, "shipping_amount": 10}]).name
		table = frappe.qb.DocType("Shipping Service")
		frappe.qb.update(table).set(table.shipping_rule, shipping_rule).where(table.name == service).run()

		self.assertEqual(get_legacy_service_rules()[service], shipping_rule)
