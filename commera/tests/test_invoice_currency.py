import frappe
from frappe.tests import IntegrationTestCase

from commera.invoice_currency import get_invoice_currency_error

MULTI_CURRENCY_FIELD = "allow_multi_currency_invoices_against_single_party_account"


class TestInvoiceCurrency(IntegrationTestCase):
	"""Can ERPNext invoice a customer in a currency other than the company's?"""

	def setUp(self):
		self.company = frappe.defaults.get_global_default("company")
		self.company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
		self.currency = "EUR" if self.company_currency == "USD" else "USD"
		self.set_multi_currency(0)

	def test_the_company_currency_is_always_invoiced(self):
		self.assertIsNone(get_invoice_currency_error(self.company, self.company_currency))

	def test_another_currency_is_refused_on_a_company_currency_receivable(self):
		refusal = f"document currency ({self.currency}) should be same"

		self.assertIn(refusal, get_invoice_currency_error(self.company, self.currency, self.make_customer()))
		# No customer stands for a new shopper, as a market check at save has none.
		self.assertIn(refusal, get_invoice_currency_error(self.company, self.currency))

	def test_another_currency_is_invoiced_when_accounts_settings_allow_it(self):
		self.set_multi_currency(1)

		self.assertIsNone(get_invoice_currency_error(self.company, self.currency, self.make_customer()))

	def test_another_currency_is_invoiced_on_a_receivable_in_that_currency(self):
		customer = self.make_customer(account=self.make_receivable_account())

		self.assertIsNone(get_invoice_currency_error(self.company, self.currency, customer))

	def test_the_refusal_reaches_no_message_log(self):
		frappe.clear_messages()
		get_invoice_currency_error(self.company, self.currency)

		self.assertFalse(frappe.get_message_log())

	def set_multi_currency(self, value):
		previous = frappe.db.get_single_value("Accounts Settings", MULTI_CURRENCY_FIELD)
		self.addCleanup(frappe.db.set_single_value, "Accounts Settings", MULTI_CURRENCY_FIELD, previous)
		frappe.db.set_single_value("Accounts Settings", MULTI_CURRENCY_FIELD, value)

	def make_customer(self, account=None):
		customer = {
			"doctype": "Customer",
			"customer_name": f"ZZ Invoice Currency {frappe.generate_hash(length=8)}",
		}
		if account:
			# ERPNext takes a receivable in a foreign currency only as the customer's billing currency.
			customer.update(
				default_currency=self.currency, accounts=[{"company": self.company, "account": account}]
			)
		return frappe.get_doc(customer).insert(ignore_permissions=True).name

	def make_receivable_account(self):
		default_receivable = frappe.get_cached_value("Company", self.company, "default_receivable_account")
		account = {
			"doctype": "Account",
			"account_name": f"ZZ Debtors {self.currency} {frappe.generate_hash(length=6)}",
			"parent_account": frappe.db.get_value("Account", default_receivable, "parent_account"),
			"company": self.company,
			"account_type": "Receivable",
			"account_currency": self.currency,
		}
		return frappe.get_doc(account).insert(ignore_permissions=True).name
