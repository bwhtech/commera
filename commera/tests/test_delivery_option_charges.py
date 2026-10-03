# Copyright (c) 2026, company@bwhstudios.com and Contributors
# Delivery options priced by the bands of the store's Shipping Rule that name them.

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.data import flt

from commera.api.shipping import (
	DELIVERY_CHARGE_DESCRIPTION,
	apply_delivery_option,
	find_option,
	get_quoted_options,
	reprice_selected_option,
)
from commera.utils import get_delivery_configuration

COMPANY = "Lifestyle Demo"
BACKUP_CHARGE = 35.0


def set_store_rule(shipping_rule: str | None):
	frappe.db.set_single_value("Commera Settings", "shipping_rule", shipping_rule)
	frappe.clear_document_cache("Commera Settings", "Commera Settings")


def get_expense_account(exclude: str | None = None) -> str:
	return frappe.db.get_value(
		"Account",
		{"company": COMPANY, "is_group": 0, "root_type": "Expense", "name": ["!=", exclude or ""]},
		"name",
	)


def make_service(title: str, backup_charge: float = BACKUP_CHARGE) -> str:
	return (
		frappe.get_doc(
			{"doctype": "Shipping Service", "title": title, "enabled": 1, "backup_charge": backup_charge}
		)
		.insert(ignore_permissions=True)
		.name
	)


def make_store_rule(bands: list[dict], account: str | None = None):
	rule = frappe.new_doc("Shipping Rule")
	rule.label = f"_Test Store Rule {frappe.generate_hash(length=6)}"
	rule.shipping_rule_type = "Selling"
	rule.calculate_based_on = "Net Total"
	rule.company = COMPANY
	rule.account = account or get_expense_account()
	rule.cost_center = frappe.db.get_value("Cost Center", {"company": COMPANY, "is_group": 0}, "name")
	for band in bands:
		rule.append("conditions", band)
	rule.insert(ignore_permissions=True)
	set_store_rule(rule.name)
	return rule


class TestDeliveryOptionCharges(IntegrationTestCase):
	def setUp(self):
		from bwh_shipping.bwh_shipping.pricing import get_enabled_services

		# The demo site has real AfterShip services, and a live rate call commits mid-test.
		live_quotes = patch("bwh_shipping.bwh_shipping.pricing.get_live_quotes", return_value={})
		live_quotes.start()
		self.addCleanup(live_quotes.stop)
		self.addCleanup(get_enabled_services.clear_cache)
		self.addCleanup(set_store_rule, frappe.db.get_single_value("Commera Settings", "shipping_rule"))

		suffix = frappe.generate_hash(length=6)
		self.standard = make_service(f"_Test Standard {suffix}")
		self.express = make_service(f"_Test Express {suffix}")
		self.customer = self.make_customer()
		self.address = self.make_address()
		self.item = self.make_item()

	def make_customer(self) -> str:
		return (
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": f"_Test Delivery Customer {frappe.generate_hash(length=6)}",
					"customer_type": "Individual",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def make_address(self) -> str:
		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": "_Test Delivery",
				"address_type": "Shipping",
				"address_line1": "1 Test Street",
				"city": "Bengaluru",
				"country": "India",
				"pincode": "560001",
			}
		)
		address.append("links", {"link_doctype": "Customer", "link_name": self.customer})
		return address.insert(ignore_permissions=True).name

	def make_item(self) -> str:
		return (
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": f"_Test Delivery Item {frappe.generate_hash(length=6)}",
					"item_group": frappe.get_all("Item Group", {"is_group": 0}, pluck="name", limit=1)[0],
					"stock_uom": "Nos",
					"is_stock_item": 0,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def make_quotation(self, rate: float, currency: str = "INR", conversion_rate: float = 1):
		quotation = frappe.new_doc("Quotation")
		quotation.quotation_to = "Customer"
		quotation.party_name = self.customer
		quotation.company = COMPANY
		quotation.order_type = "Shopping Cart"
		quotation.currency = currency
		quotation.conversion_rate = conversion_rate
		quotation.shipping_address_name = self.address
		quotation.append("items", {"item_code": self.item, "qty": 1, "rate": rate})
		quotation.insert(ignore_permissions=True)
		return quotation

	def choose(self, quotation, title: str):
		apply_delivery_option(quotation, find_option(quotation, title))

	def get_option(self, quotation, title: str) -> dict:
		return next(option for option in get_quoted_options(quotation) if option["title"] == title)

	def get_delivery_rows(self, quotation) -> list:
		return [
			row for row in quotation.taxes if (row.description or "").startswith(DELIVERY_CHARGE_DESCRIPTION)
		]

	def make_tiered_rule(self, account: str | None = None):
		return make_store_rule(
			[
				{"from_value": 0, "to_value": 500, "shipping_amount": 100, "shipping_service": self.express},
				{
					"from_value": 500,
					"to_value": 1000,
					"shipping_amount": 50,
					"shipping_service": self.express,
				},
				{"from_value": 1000, "to_value": 0, "shipping_amount": 0, "shipping_service": self.express},
			],
			account=account,
		)

	def make_free_above_rule(self):
		return make_store_rule(
			[
				{"from_value": 0, "to_value": 100, "shipping_amount": 50, "shipping_service": self.standard},
				{
					"from_value": 100,
					"to_value": 0,
					"shipping_amount": 0,
					"free_shipping": 1,
					"shipping_service": self.standard,
				},
			]
		)

	def test_options_are_priced_by_the_store_rule_band_that_names_them(self):
		self.make_tiered_rule()
		quotation = self.make_quotation(rate=80)

		self.assertEqual(flt(self.get_option(quotation, self.express)["amount"]), 100.0)
		# No band names the standard option, so it keeps its own backup charge.
		self.assertEqual(flt(self.get_option(quotation, self.standard)["amount"]), BACKUP_CHARGE)

	def test_free_above_threshold_waives_the_charge(self):
		self.make_free_above_rule()
		quotation = self.make_quotation(rate=150)

		self.choose(quotation, self.standard)

		self.assertEqual(self.get_delivery_rows(quotation), [])
		self.assertEqual(flt(quotation.custom_delivery_charge), 0)

	def test_a_free_band_shows_the_option_free_and_it_stays_free_at_payment(self):
		self.make_free_above_rule()
		quotation = self.make_quotation(rate=150)
		self.assertTrue(self.get_option(quotation, self.standard)["is_free"])
		self.choose(quotation, self.standard)
		quotation.save(ignore_permissions=True)

		self.assertTrue(reprice_selected_option(quotation))
		self.assertEqual(self.get_delivery_rows(quotation), [])

	def test_a_free_option_stays_free_when_it_can_no_longer_be_quoted(self):
		self.make_free_above_rule()
		quotation = self.make_quotation(rate=150)
		self.choose(quotation, self.standard)
		quotation.save(ignore_permissions=True)

		# Without the stored 0 the fallback would re-price from the backup charge and bill the shopper.
		from bwh_shipping.bwh_shipping.pricing import get_enabled_services

		frappe.db.set_value("Shipping Service", self.standard, "enabled", 0)
		get_enabled_services.clear_cache()
		set_store_rule(None)

		self.assertTrue(reprice_selected_option(quotation))
		self.assertEqual(self.get_delivery_rows(quotation), [])
		self.assertEqual(flt(quotation.custom_delivery_charge), 0)

	def test_linked_option_posts_fee_against_rule_account(self):
		charge_account_head = frappe.db.get_single_value("Commera Settings", "charge_account_head")
		rule_account = get_expense_account(exclude=charge_account_head)
		self.make_tiered_rule(account=rule_account)
		quotation = self.make_quotation(rate=80)

		self.choose(quotation, self.express)

		rows = self.get_delivery_rows(quotation)
		self.assertEqual(len(rows), 1)
		self.assertEqual(flt(rows[0].tax_amount), 100.0)
		self.assertEqual(rows[0].account_head, rule_account)

	def test_multicurrency_fee_is_converted_and_matches_displayed_rate(self):
		rule = self.make_tiered_rule()
		# 5 USD at 80 is 400 INR of base net total, inside the 0-500 band of 100 INR.
		quotation = self.make_quotation(rate=5, currency="USD", conversion_rate=80)
		self.assertEqual(flt(quotation.base_net_total), 400.0)
		expected_fee = flt(100.0 / 80, 2)

		self.assertEqual(flt(self.get_option(quotation, self.express)["amount"]), expected_fee)

		self.choose(quotation, self.express)
		rows = self.get_delivery_rows(quotation)
		self.assertEqual(len(rows), 1)
		self.assertEqual(flt(rows[0].tax_amount), expected_fee)
		self.assertEqual(rows[0].account_head, rule.account)

	def test_delivery_configuration_reads_the_threshold_from_the_free_band(self):
		make_store_rule(
			[
				{"from_value": 0, "to_value": 60, "shipping_amount": 50},
				{"from_value": 60, "to_value": 100, "shipping_amount": 30},
				{"from_value": 100, "to_value": 0, "free_shipping": 1},
			]
		)

		self.assertEqual(get_delivery_configuration(), (50, 100))

	def test_delivery_configuration_without_a_free_band_reads_the_first_band(self):
		self.make_tiered_rule()

		self.assertEqual(get_delivery_configuration(), (100, 500))
