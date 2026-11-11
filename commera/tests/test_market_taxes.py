from unittest.mock import Mock, patch

import frappe
from frappe.utils.data import flt

from commera.api.payment_hooks import on_payment_request_update
from commera.api.payments import generate_quotation_for_cart
from commera.api.shipping import DELIVERY_CHARGE_DESCRIPTION, get_charge_amount
from commera.cart_taxes import TEMPLATE_DOCTYPE, apply_market_taxes
from commera.commera_ecommerce.doctype.commera_cart.commera_cart import get_session_cart
from commera.localization import pin_localization, resolve
from commera.localization.markets import StorefrontMarkets
from commera.tests.test_admin_orders import ensure_fiscal_year
from commera.tests.test_market_cart import MarketCartTestCase
from commera.tests.test_market_orders import use_company_warehouse
from commera.utils import get_store_company

GATEWAY = "ZZ Market Tax Gateway"
MARKET_MODULE = "commera.commera_ecommerce.doctype.commera_market.commera_market"


class MarketTaxTestCase(MarketCartTestCase):
	"""Gulf sells the item at 300. Its taxes come from the templates each test sets."""

	def setUp(self):
		super().setUp()
		# A shipping rule would add its charge to every grand total here.
		self.set_single("Commera Settings", "shipping_rule", None)
		self.company = get_store_company()
		self.account = make_tax_account(self.company)
		self.item_code = self.item("TAXED", market_sale=300)

	def make_template(self, rate, inclusive=0, is_default=0):
		template = {
			"doctype": TEMPLATE_DOCTYPE,
			"title": f"ZZ Market Tax {frappe.generate_hash(length=8)}",
			"company": self.company,
			"is_default": is_default,
			"taxes": [
				{
					"charge_type": "On Net Total",
					"account_head": self.account,
					"rate": rate,
					"description": f"VAT {rate}%",
					"included_in_print_rate": inclusive,
				}
			],
		}
		return frappe.get_doc(template).insert(ignore_permissions=True).name

	def set_market_template(self, template):
		market = frappe.get_doc("Commera Market", "gulf")
		market.tax_template = template
		market.save(ignore_permissions=True)

	def quote_in_market(self):
		self.sign_in_shopper()
		with self.in_market():
			self.add(self.item_code)
			return generate_quotation_for_cart({})

	def in_arabic_market(self):
		return pin_localization(resolve("/ar-ae/")[0])


class TestMarketTaxTemplate(MarketTaxTestCase):
	def test_an_exclusive_template_adds_tax_on_top_of_the_price(self):
		template = self.make_template(10)
		self.set_market_template(template)

		quotation = self.quote_in_market()

		self.assertEqual(quotation.taxes_and_charges, template)
		self.assertEqual([row.included_in_print_rate for row in quotation.taxes], [0])
		self.assertEqual((quotation.net_total, quotation.total_taxes_and_charges), (300, 30))
		self.assertEqual(quotation.grand_total, 330)

	def test_an_inclusive_template_takes_tax_out_of_the_price(self):
		template = self.make_template(10, inclusive=1)
		self.set_market_template(template)

		quotation = self.quote_in_market()

		self.assertEqual(quotation.taxes_and_charges, template)
		self.assertEqual([row.included_in_print_rate for row in quotation.taxes], [1])
		self.assertEqual(quotation.grand_total, 300)
		self.assertEqual(flt(quotation.net_total, 2), 272.73)
		self.assertEqual(flt(quotation.total_taxes_and_charges, 2), 27.27)

	def test_the_cart_price_preview_uses_the_market_template(self):
		template = self.make_template(10)
		self.set_market_template(template)
		self.sign_in_shopper()

		with self.in_market():
			self.add(self.item_code)
			preview = get_session_cart().get_quotation_preview()

		self.assertEqual((preview.taxes_and_charges, preview.grand_total), (template, 330))

	def test_a_market_without_a_template_uses_the_company_default(self):
		default = self.make_template(5, is_default=1)

		in_market = self.quote_in_market()
		in_store = generate_quotation_for_cart({})

		self.assertEqual((in_market.taxes_and_charges, in_market.grand_total), (default, 315))
		# The primary market keeps its behavior: ERPNext's tax rules only, none here.
		self.assertEqual((in_store.taxes_and_charges, in_store.taxes), (None, []))
		self.assertEqual(in_store.grand_total, 80)

	def test_a_switch_replaces_the_taxes_of_the_same_quotation(self):
		self.set_market_template(self.make_template(10))
		quotation = self.quote_in_market()

		in_store = generate_quotation_for_cart({})
		with self.in_market():
			back_in_market = generate_quotation_for_cart({})

		self.assertEqual(in_store.name, quotation.name)
		self.assertEqual((in_store.taxes_and_charges, in_store.taxes, in_store.grand_total), (None, [], 80))
		self.assertEqual((back_in_market.grand_total, len(back_in_market.taxes)), (330, 1))

	def test_a_switch_keeps_the_delivery_charge_after_the_new_taxes(self):
		old, new = self.make_template(10), self.make_template(5)
		self.set_market_template(new)
		quotation = frappe.new_doc("Quotation", company=self.company, taxes_and_charges=old)
		quotation.append("taxes", {"charge_type": "On Net Total", "account_head": self.account, "rate": 10})
		delivery = {"description": f"{DELIVERY_CHARGE_DESCRIPTION} - Express", "charge_type": "Actual"}
		quotation.append("taxes", {**delivery, "account_head": self.account, "tax_amount": 15})

		apply_market_taxes(quotation, StorefrontMarkets.load().find("gulf"), switched=True)

		rows = [(row.idx, row.description, row.tax_amount) for row in quotation.taxes]
		self.assertEqual(quotation.taxes_and_charges, new)
		self.assertEqual(rows, [(1, "VAT 5%", 0), (2, delivery["description"], 15)])

	def test_a_disabled_template_falls_back_to_the_company_default(self):
		template = self.make_template(10)
		default = self.make_template(5, is_default=1)
		self.set_market_template(template)
		frappe.db.set_value(TEMPLATE_DOCTYPE, template, "disabled", 1)

		quotation = self.quote_in_market()

		self.assertEqual((quotation.taxes_and_charges, quotation.grand_total), (default, 315))


class TestMarketTaxTemplateValidation(MarketTaxTestCase):
	def test_a_template_of_another_company_is_refused(self):
		template = self.make_template(10)

		with (
			patch(f"{MARKET_MODULE}.get_store_company", return_value="ZZ Other Company"),
			self.assertRaisesRegex(frappe.ValidationError, "Choose a template of the store company"),
		):
			self.set_market_template(template)

	def test_a_disabled_template_is_refused(self):
		template = self.make_template(10)
		frappe.db.set_value(TEMPLATE_DOCTYPE, template, "disabled", 1)

		with self.assertRaisesRegex(frappe.ValidationError, "is disabled"):
			self.set_market_template(template)

	def test_a_template_of_the_store_company_is_kept(self):
		template = self.make_template(10)

		self.set_market_template(template)

		self.assertEqual(frappe.db.get_value("Commera Market", "gulf", "tax_template"), template)


class TestMarketOrderRecords(MarketTaxTestCase):
	"""A gateway-paid order: the webhook places it outside any market."""

	def setUp(self):
		super().setUp()
		ensure_fiscal_year()
		use_company_warehouse(self)
		mode_of_payment = {"doctype": "Mode of Payment", "mode_of_payment": GATEWAY, "type": "Bank"}
		frappe.get_doc(mode_of_payment).insert(ignore_permissions=True, ignore_if_duplicate=True)

	def test_the_quotation_and_order_record_market_language_and_taxes(self):
		template = self.make_template(10)
		self.set_market_template(template)
		self.sign_in_shopper()
		with self.in_arabic_market():
			self.add(self.item_code)
			quotation = generate_quotation_for_cart({})
		frappe.set_user("Administrator")

		sales_order = self.pay(quotation)

		for doc in (quotation, sales_order):
			with self.subTest(doctype=doc.doctype):
				self.assertEqual((doc.commera_market, doc.language), ("gulf", "ar"))
				self.assertEqual((doc.taxes_and_charges, doc.grand_total), (template, 330))

	def test_the_primary_market_records_its_handle_and_language(self):
		self.sign_in_shopper()
		self.add(self.item_code)

		quotation = generate_quotation_for_cart({})

		self.assertEqual((quotation.commera_market, quotation.language), ("primary", "en"))

	def pay(self, quotation):
		quotation = frappe.get_doc("Quotation", quotation.name)
		payment_request = frappe._dict(
			status="Paid",
			ref_doctype="Quotation",
			ref_docname=quotation.name,
			gateway=GATEWAY,
			amount=get_charge_amount(quotation),
			currency_code=quotation.currency,
			order_ref="pi_zz_market_tax",
		)
		payment_request.db_set = Mock()
		# Billing needs a gateway Mode of Payment; placement is what this tests.
		with patch("commera.api.payments.create_sales_invoice"):
			on_payment_request_update(payment_request)
		return frappe.get_doc("Sales Order", payment_request.db_set.call_args.args[0]["ref_docname"])


def make_tax_account(company):
	parent_account = frappe.get_all(
		"Account", {"company": company, "root_type": "Liability", "is_group": 1}, pluck="name", limit=1
	)[0]
	account = {
		"doctype": "Account",
		"account_name": f"ZZ Market VAT {frappe.generate_hash(length=6)}",
		"parent_account": parent_account,
		"company": company,
		"account_type": "Tax",
	}
	return frappe.get_doc(account).insert(ignore_permissions=True).name
