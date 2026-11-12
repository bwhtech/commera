import frappe
from frappe.utils.data import add_days, today

from commera.api.payments import generate_quotation_for_cart, update_quotation_address
from commera.commera_ecommerce.doctype.commera_cart.commera_cart import get_session_cart
from commera.commera_ecommerce.doctype.commera_market.commera_market import get_country_code
from commera.core import _get_cart_quotation, get_party
from commera.localization import pin_localization, resolve
from commera.tests.test_market_taxes import MarketTaxTestCase
from commera.tests.test_markets import UAE

OTHER_COUNTRY = "Egypt"


class TestCartTaxRules(MarketTaxTestCase):
	"""The store taxes its own country at 15% with a Tax Rule. Gulf sells at 300, the store at 80."""

	def setUp(self):
		super().setUp()
		self.store_country = frappe.get_cached_value("Company", self.company, "country")
		self.vat = self.make_template(15)

	def test_a_round_trip_through_a_market_keeps_the_store_vat(self):
		self.make_tax_rule(self.vat, shipping_country=self.store_country)
		self.set_market_template(self.make_template(10))
		self.quote_in_store()
		update_quotation_address(self.new_address(self.store_country))
		home = _get_cart_quotation().customer_address
		with self.in_market():
			generate_quotation_for_cart({})
			update_quotation_address(self.new_address(UAE))

		generate_quotation_for_cart({})
		update_quotation_address(self.saved_address(home))

		quotation = _get_cart_quotation()
		self.assertEqual(quotation.taxes_and_charges, self.vat)
		self.assertEqual(self.get_taxes(quotation), [("VAT 15%", 12)])
		self.assertEqual(quotation.grand_total, 92)

	def test_a_store_country_rule_does_not_tax_a_market_cart_without_an_address(self):
		self.make_tax_rule(self.vat, shipping_country=self.store_country)

		quotation = self.quote_in_market()
		with self.in_market():
			preview = get_session_cart().get_quotation_preview()

		for doc in (quotation, preview):
			with self.subTest(doctype=doc.doctype):
				self.assertEqual((doc.taxes_and_charges, self.get_taxes(doc)), (None, []))
				self.assertEqual(doc.grand_total, 300)

	def test_a_new_address_outside_the_rule_country_removes_its_tax(self):
		self.make_tax_rule(self.vat, shipping_country=self.store_country)
		quotation = self.quote_in_store()
		self.assertEqual((quotation.taxes_and_charges, quotation.grand_total), (self.vat, 92))

		update_quotation_address(self.new_address(OTHER_COUNTRY))

		quotation = _get_cart_quotation()
		self.assertEqual((quotation.taxes_and_charges, self.get_taxes(quotation)), (None, []))
		self.assertEqual(quotation.grand_total, 80)

	def test_a_tax_rule_for_the_customer_beats_the_market_template(self):
		self.set_market_template(self.make_template(10))
		zero_rated = self.make_template(0)
		exempt = make_tax_category()
		self.make_tax_rule(zero_rated, tax_category=exempt)
		self.sign_in_shopper()
		frappe.db.set_value("Customer", get_party().name, "tax_category", exempt)

		with self.in_market():
			self.add(self.item_code)
			quotation = generate_quotation_for_cart({})

		self.assertEqual((quotation.taxes_and_charges, quotation.grand_total), (zero_rated, 300))

	def test_a_dated_tax_rule_taxes_the_cart_on_its_dates(self):
		self.make_tax_rule(
			self.vat,
			shipping_country=self.store_country,
			from_date=add_days(today(), -1),
			to_date=add_days(today(), 30),
		)

		quotation = self.quote_in_store()

		self.assertEqual((quotation.taxes_and_charges, quotation.grand_total), (self.vat, 92))

	def test_a_generic_rule_does_not_override_the_market_template(self):
		market_template = self.make_template(10)
		self.set_market_template(market_template)
		self.make_tax_rule(self.vat, customer_group="")
		quotation = self.quote_in_market()
		self.assertEqual((quotation.taxes_and_charges, quotation.grand_total), (market_template, 330))

	def test_a_country_rule_beats_the_market_template(self):
		self.set_market_template(self.make_template(10))
		self.make_tax_rule(self.vat, shipping_country=UAE)
		quotation = self.quote_in_market()
		self.assertEqual((quotation.taxes_and_charges, quotation.grand_total), (self.vat, 345))

	def test_specific_rules_keep_erpnext_priority_order(self):
		self.set_market_template(self.make_template(10))
		self.make_tax_rule(self.make_template(12), shipping_country=UAE, priority=2)
		self.make_tax_rule(self.vat, shipping_country=UAE, priority=1)
		quotation = self.quote_in_market()
		self.assertEqual((quotation.taxes_and_charges, quotation.grand_total), (self.vat, 345))

	def test_guest_previews_use_country_rules(self):
		from commera.discounts.preview import get_preview_quotation

		self.make_tax_rule(self.vat, shipping_country=self.store_country)
		with pin_localization(resolve("/", country=get_country_code(self.store_country))[0]):
			quotation = get_preview_quotation([{"item_code": self.item_code, "qty": 1}], user="Guest")
		self.assertEqual((quotation.taxes_and_charges, quotation.grand_total), (self.vat, 92))

	def test_guest_previews_do_not_use_a_named_customer_rule(self):
		from commera.discounts.preview import get_preview_quotation

		self.sign_in_shopper()
		self.make_tax_rule(self.vat, customer=get_party().name)
		quotation = get_preview_quotation([{"item_code": self.item_code, "qty": 1}], user="Guest")
		self.assertIsNone(quotation.taxes_and_charges)
		self.assertEqual(quotation.grand_total, 80)

	def test_an_unclaimed_country_does_not_use_the_store_country_rule(self):
		from commera.cart_taxes import get_market_country, get_tax_rule_template

		self.make_tax_rule(self.vat, shipping_country=self.store_country)
		with pin_localization(resolve("/", country="EG")[0]) as localization:
			quotation = frappe.new_doc("Quotation", company=self.company, quotation_to="Customer")
			self.assertEqual(get_market_country(localization.market), OTHER_COUNTRY)
			self.assertIsNone(get_tax_rule_template(quotation, localization.market))

	def quote_in_store(self):
		self.sign_in_shopper()
		self.add(self.item_code)
		return generate_quotation_for_cart({})

	def make_tax_rule(self, template, **conditions):
		rule = {
			"doctype": "Tax Rule",
			"tax_type": "Sales",
			"sales_tax_template": template,
			"company": self.company,
			"use_for_shopping_cart": 1,
			**conditions,
		}
		name = frappe.get_doc(rule).insert(ignore_permissions=True).name
		# A later test's rule on the same conditions would conflict with this one.
		self.addCleanup(frappe.delete_doc, "Tax Rule", name, force=True, ignore_permissions=True)
		return name

	def new_address(self, country):
		billing = {
			"full_address": "1 Tax Street",
			"city": "Capital",
			"country": country,
			"phone_number": "+966500000001",
			"email": frappe.session.user,
			"first_name": "ZZ",
			"last_name": "Shopper",
		}
		return {"billing_address": billing, "shipping_same_as_billing": True}

	def saved_address(self, name):
		return {"billing_address": {"is_saved": True, "address_id": name}, "shipping_same_as_billing": True}

	def get_taxes(self, doc):
		return [(row.description, row.tax_amount) for row in doc.taxes]


def make_tax_category():
	title = f"ZZ Exempt {frappe.generate_hash(length=6)}"
	return frappe.get_doc({"doctype": "Tax Category", "title": title}).insert(ignore_permissions=True).name
