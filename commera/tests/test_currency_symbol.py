# Copyright (c) 2026, company@bwhstudios.com and contributors

import frappe
from frappe.tests import IntegrationTestCase

from commera.utils import get_currency_symbol, get_store_company


class TestCurrencySymbol(IntegrationTestCase):
	def set_store_currency(self, currency_name, symbol):
		if not frappe.db.exists("Currency", currency_name):
			frappe.get_doc({"doctype": "Currency", "currency_name": currency_name}).insert()
		frappe.db.set_value("Currency", currency_name, "symbol", symbol)
		# Set past validation: ERPNext refuses a new default currency once the company has transactions.
		company = get_store_company()
		original_currency = frappe.db.get_value("Company", company, "default_currency")
		frappe.db.set_value("Company", company, "default_currency", currency_name)
		self.addCleanup(self.restore_store_currency, company, currency_name, original_currency)
		self.clear_currency_cache(company, currency_name)

	def restore_store_currency(self, company, currency_name, original_currency):
		frappe.db.set_value("Company", company, "default_currency", original_currency)
		self.clear_currency_cache(company, currency_name)

	def clear_currency_cache(self, company, currency_name):
		frappe.clear_document_cache("Company", company)
		frappe.clear_document_cache("Currency", currency_name)

	def test_currency_without_symbol_falls_back_to_its_code(self):
		self.set_store_currency("XTS", None)
		self.assertEqual(get_currency_symbol(), "XTS\u00a0")

	def test_currency_with_symbol_returns_the_symbol(self):
		self.set_store_currency("XTS", "¤")
		self.assertEqual(get_currency_symbol(), "¤")
