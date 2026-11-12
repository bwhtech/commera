"""A market is refused when ERPNext would refuse its checkout: the merchant hears it on save,
not a shopper at checkout."""

import frappe
from frappe.tests import IntegrationTestCase

from commera.localization.market_setup import MULTI_CURRENCY_FIELD, validate_markets_for_store
from commera.tests.test_admin_orders import make_shipping_rule, make_test_sales_order
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_market_prices import get_other_currency, make_price_list
from commera.tests.test_markets import UAE, allow_multi_currency_invoices, make_market, use_markets


class MarketSetupTestCase(IntegrationTestCase):
	"""Gulf sells to the UAE from its own price list, in another currency than the store."""

	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		use_markets(self)
		self.set_single("Commera Settings", "shipping_rule", None)
		self.sale = make_price_list("Setup Sale", get_other_currency())
		self.market = make_market("Gulf", [UAE], "ar", ["en"], handle="gulf", sale_price_list=self.sale)

	def set_single(self, doctype, fieldname, value):
		previous = frappe.db.get_single_value(doctype, fieldname)
		self.addCleanup(self.write_single, doctype, fieldname, previous)
		self.write_single(doctype, fieldname, value)

	def write_single(self, doctype, fieldname, value):
		frappe.db.set_single_value(doctype, fieldname, value)
		frappe.clear_document_cache(doctype, doctype)

	def save_price_list(self, **values):
		price_list = frappe.get_doc("Price List", self.sale)
		price_list.update(values)
		price_list.save()


class TestMarketPriceLists(MarketSetupTestCase):
	def test_a_market_refuses_a_disabled_sale_price_list(self):
		frappe.db.set_value("Price List", self.sale, "enabled", 0)

		with self.assertRaisesRegex(frappe.ValidationError, "is disabled"):
			self.market.save()

	def test_a_market_price_list_cannot_be_disabled(self):
		with self.assertRaisesRegex(frappe.ValidationError, "must stay enabled and selling"):
			self.save_price_list(enabled=0)

	def test_a_market_price_list_cannot_stop_selling(self):
		with self.assertRaisesRegex(frappe.ValidationError, "must stay enabled and selling"):
			self.save_price_list(selling=0, buying=1)

	def test_a_price_list_of_no_market_can_be_disabled(self):
		other = make_price_list("Setup Other", get_other_currency())
		price_list = frappe.get_doc("Price List", other)
		price_list.enabled = 0

		price_list.save()


class TestMarketPriceListCountries(MarketSetupTestCase):
	def test_every_market_country_must_be_a_sale_price_list_country(self):
		restricted = frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": f"Setup Saudi Only {frappe.generate_hash(length=6)}",
				"currency": get_other_currency(),
				"selling": 1,
				"countries": [{"country": "Saudi Arabia"}],
			}
		).insert()
		self.market.sale_price_list = restricted.name

		with self.assertRaisesRegex(frappe.ValidationError, "is not applicable for country"):
			self.market.save()

	def test_a_sale_price_list_cannot_leave_out_a_market_country(self):
		with self.assertRaisesRegex(frappe.ValidationError, "in its countries, or remove it from the market"):
			self.save_price_list(countries=[{"country": "Saudi Arabia"}])

	def test_a_sale_price_list_may_name_its_market_countries(self):
		self.save_price_list(countries=[{"country": UAE}, {"country": "Saudi Arabia"}])

		self.market.save()


class TestMarketDeletion(MarketSetupTestCase):
	def test_a_market_with_an_order_cannot_be_deleted(self):
		order = make_test_sales_order(submit=False)
		frappe.db.set_value("Sales Order", order.name, "commera_market", "gulf")
		# The class rolls back only after its last test.
		self.addCleanup(frappe.db.set_value, "Sales Order", order.name, "commera_market", None)

		with self.assertRaisesRegex(frappe.LinkExistsError, order.name):
			frappe.delete_doc("Commera Market", "gulf")
		self.assertTrue(frappe.db.exists("Commera Market", "gulf"))

	def test_a_market_with_an_open_cart_cannot_be_deleted(self):
		cart = {"doctype": "Commera Cart", "cart_key": frappe.generate_hash(), "market": "gulf"}
		cart = frappe.get_doc(cart).insert(ignore_permissions=True)
		self.addCleanup(frappe.db.delete, "Commera Cart", cart.name)

		with self.assertRaisesRegex(frappe.LinkExistsError, "Disable the market instead"):
			frappe.delete_doc("Commera Market", "gulf")

	def test_robots_txt_drops_a_deleted_market(self):
		self.set_single("Website Settings", "robots_txt", "")
		self.market.save()
		self.assertIn("/en-ae/cart", frappe.db.get_single_value("Website Settings", "robots_txt"))

		frappe.delete_doc("Commera Market", "gulf")

		self.assertNotIn("/en-ae/", frappe.db.get_single_value("Website Settings", "robots_txt"))


class TestMarketDelivery(MarketSetupTestCase):
	def use_store_rule(self, countries):
		rule = make_shipping_rule(10)
		rule.set("countries", [{"country": country} for country in countries])
		rule.save()
		self.set_single("Commera Settings", "shipping_rule", rule.name)
		return rule

	def test_every_market_country_needs_the_store_shipping_rule(self):
		self.use_store_rule(["Saudi Arabia"])

		with self.assertRaisesRegex(frappe.ValidationError, "does not deliver to"):
			self.market.save()

	def test_a_rule_without_countries_delivers_everywhere(self):
		self.use_store_rule([])

		self.market.save()

	def test_the_store_shipping_rule_cannot_drop_a_market_country(self):
		rule = self.use_store_rule(["Saudi Arabia", UAE])
		rule.set("countries", [{"country": "Saudi Arabia"}])

		with self.assertRaisesRegex(frappe.ValidationError, "in its countries, or remove it from the market"):
			rule.save()

	def test_a_new_store_shipping_rule_must_deliver_to_every_market(self):
		settings = frappe.get_doc("Commera Settings")
		settings.shipping_rule = self.make_saudi_rule()

		with self.assertRaisesRegex(frappe.ValidationError, "does not deliver to"):
			validate_markets_for_store(settings)

	def make_saudi_rule(self):
		rule = make_shipping_rule(10)
		rule.append("countries", {"country": "Saudi Arabia"})
		rule.save()
		return rule.name


class TestMarketInvoiceCurrency(MarketSetupTestCase):
	def test_a_market_in_another_currency_needs_multi_currency_invoices(self):
		allow_multi_currency_invoices(self, 0)

		with self.assertRaisesRegex(frappe.ValidationError, "ERPNext can invoice orders in"):
			self.market.save()

	def test_a_market_in_the_store_currency_needs_no_multi_currency_invoices(self):
		allow_multi_currency_invoices(self, 0)

		make_market("Gulf North", ["Kuwait"], "ar", handle="gulf-north")

	def test_multi_currency_invoices_stay_on_while_a_market_needs_them(self):
		settings = frappe.get_doc("Accounts Settings")
		settings.set(MULTI_CURRENCY_FIELD, 0)

		with self.assertRaisesRegex(frappe.ValidationError, "sells in another currency than"):
			settings.save()
