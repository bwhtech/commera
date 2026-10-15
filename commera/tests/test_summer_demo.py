# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

"""The Summer demo is seeded in the company's own currency, into a company the setup wizard finished."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera import install_summer_demo as demo

COMPANY = "ZZ Demo Company"
FREIGHT = "Freight and Forwarding Charges"


def get_test_company() -> str:
	"""An IDR company on ERPNext's standard chart: a bare CI site has no company at all."""
	if not frappe.db.exists("Company", COMPANY):
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": COMPANY,
				"abbr": "ZZDC",
				"default_currency": "IDR",
				"country": "Indonesia",
				"chart_of_accounts": "Standard",
			}
		).insert(ignore_permissions=True)

	return COMPANY


class TestCurrencyProfile(IntegrationTestCase):
	def test_curated_currency_keeps_its_local_prices(self):
		profile = demo.get_currency_profile("IDR")

		self.assertEqual(profile["flat_shipping_charge"], 15000)
		self.assertEqual(profile["symbol"], "Rp")
		self.assertEqual(demo.to_local_price(15, profile), 239999)

	def test_other_currency_is_derived_from_the_usd_rate(self):
		with patch.object(demo, "get_exchange_rate", return_value=0.9):
			profile = demo.get_currency_profile("EUR")

		self.assertEqual(profile["price_multiplier"], 0.9)
		self.assertEqual(profile["price_rounding"], 1)
		self.assertEqual(profile["flat_shipping_charge"], 6)
		self.assertEqual(profile["free_shipping_above"], 72)
		self.assertEqual(demo.to_local_price(129, profile), 115)

	def test_rounding_step_follows_the_rate_magnitude(self):
		with patch.object(demo, "get_exchange_rate", return_value=16250):
			profile = demo.get_currency_profile("VND")

		self.assertEqual(profile["price_rounding"], 10000)
		self.assertEqual(profile["flat_shipping_charge"], 110000)

	def test_currency_without_a_rate_is_refused(self):
		with (
			patch.object(demo, "get_exchange_rate", return_value=0),
			self.assertRaises(frappe.ValidationError),
		):
			demo.get_currency_profile("EUR")


class TestDemoCompany(IntegrationTestCase):
	def test_no_company_asks_for_setup(self):
		with (
			patch.object(demo, "get_company", return_value=None),
			self.assertRaisesRegex(frappe.ValidationError, "set up a company"),
		):
			demo.get_demo_company()

	def test_company_without_a_chart_asks_for_setup(self):
		company = get_test_company()
		real_exists = frappe.db.exists

		def no_accounts(doctype, *args, **kwargs):
			return None if doctype == "Account" else real_exists(doctype, *args, **kwargs)

		with (
			patch.object(demo, "get_company", return_value=company),
			patch.object(frappe.db, "exists", side_effect=no_accounts),
			self.assertRaisesRegex(frappe.ValidationError, "chart of accounts"),
		):
			demo.get_demo_company()

	def test_set_up_company_is_returned(self):
		company = get_test_company()
		with patch.object(demo, "get_company", return_value=company):
			self.assertEqual(demo.get_demo_company(), company)


class TestStoreCurrency(IntegrationTestCase):
	def test_alignment_leaves_the_company_and_its_accounts_alone(self):
		company = get_test_company()
		account = frappe.db.get_value("Account", {"company": company, "is_group": 0}, "name")
		frappe.db.set_value("Account", account, "account_currency", "USD")

		with patch.object(demo, "get_company", return_value=company):
			demo.align_store_currency("IDR")

		self.assertEqual(frappe.db.get_value("Company", company, "default_currency"), "IDR")
		self.assertEqual(frappe.db.get_value("Account", account, "account_currency"), "USD")


class TestFreightAccount(IntegrationTestCase):
	def test_chart_without_freight_account_gets_one(self):
		company = get_test_company()
		frappe.db.delete("Account", {"company": company, "account_name": FREIGHT})

		with patch.object(demo, "get_company", return_value=company):
			account = demo.get_freight_account()
			self.assertEqual(demo.get_freight_account(), account)

		self.assertEqual(
			frappe.db.get_value("Account", account, ["company", "root_type", "is_group"], as_dict=True),
			{"company": company, "root_type": "Expense", "is_group": 0},
		)
		self.assertEqual(frappe.db.count("Account", {"company": company, "account_name": FREIGHT}), 1)
