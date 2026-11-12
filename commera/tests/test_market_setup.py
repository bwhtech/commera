"""A market is refused when ERPNext would refuse its checkout: the merchant hears it on save,
not a shopper at checkout."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.localization.market_setup import MULTI_CURRENCY_FIELD, MarketStoreFit, validate_markets_for_store
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
			self.market.validate_price_lists()

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

		with patch("commera.localization.market_setup.has_delivery_services", return_value=False):
			with self.assertRaisesRegex(frappe.ValidationError, "does not deliver to"):
				MarketStoreFit(self.market).validate_delivery_countries()

	def test_a_rule_without_countries_delivers_everywhere(self):
		self.use_store_rule([])

		self.market.save()

	def test_the_store_shipping_rule_cannot_drop_a_market_country(self):
		rule = self.use_store_rule(["Saudi Arabia", UAE])
		rule.set("countries", [{"country": "Saudi Arabia"}])

		with patch("commera.localization.market_setup.has_delivery_services", return_value=False):
			with self.assertRaisesRegex(
				frappe.ValidationError, "in its countries, or remove it from the market"
			):
				rule.save()

	def test_a_new_store_shipping_rule_must_deliver_to_every_market(self):
		settings = frappe.get_doc("Commera Settings")
		settings.shipping_rule = self.make_saudi_rule()

		with patch("commera.localization.market_setup.has_delivery_services", return_value=False):
			with self.assertRaisesRegex(frappe.ValidationError, "does not deliver to"):
				validate_markets_for_store(settings)

	def make_saudi_rule(self):
		rule = make_shipping_rule(10)
		rule.append("countries", {"country": "Saudi Arabia"})
		rule.save()
		return rule.name

	def test_patch_stamps_bands_with_existing_country_gap(self):
		from commera.patches.move_service_shipping_rules_to_store_rule import stamp_store_rule_bands

		rule = self.use_store_rule(["Saudi Arabia"])
		rule.set("conditions", [{"from_value": 0, "to_value": 0, "shipping_amount": 10}])
		rule.db_update()
		rule.update_children()
		with patch("commera.localization.market_setup.has_delivery_services", return_value=False):
			stamp_store_rule_bands(rule.name, [None])

	def test_coverage_can_expand_without_repairing_all_missing_countries(self):
		rule = self.use_store_rule(["Saudi Arabia"])
		rule.append("countries", {"country": "Kuwait"})
		with patch("commera.localization.market_setup.has_delivery_services", return_value=False):
			rule.save()

	def test_patch_skips_even_a_reduction_in_coverage(self):
		rule = self.use_store_rule(["Saudi Arabia", UAE])
		rule.set("countries", [{"country": "Saudi Arabia"}])
		with (
			patch.dict(frappe.flags, {"in_patch": True}),
			patch("commera.localization.market_setup.has_delivery_services", return_value=False),
		):
			rule.save()


class TestMarketInvoiceCurrency(MarketSetupTestCase):
	def test_a_market_in_another_currency_needs_multi_currency_invoices(self):
		allow_multi_currency_invoices(self, 0)

		with self.assertRaisesRegex(frappe.ValidationError, "ERPNext can invoice orders in"):
			MarketStoreFit(self.market).validate_invoice_currency()

	def test_a_market_in_the_store_currency_needs_no_multi_currency_invoices(self):
		allow_multi_currency_invoices(self, 0)

		make_market("Gulf North", ["Kuwait"], "ar", handle="gulf-north")

	def test_accounts_settings_can_turn_off_multi_currency_invoices(self):
		settings = frappe.get_doc("Accounts Settings")
		settings.set(MULTI_CURRENCY_FIELD, 0)

		settings.save()


class TestMarketRepairs(MarketSetupTestCase):
	def test_disabling_and_renaming_do_not_validate_existing_currency(self):
		allow_multi_currency_invoices(self, 0)
		self.market.market_name = "Repaired name"
		self.market.save()
		self.market.enabled = 0
		self.market.save()
		self.market.enabled = 1
		with self.assertRaisesRegex(frappe.ValidationError, "ERPNext can invoice"):
			self.market.save()

	def test_disabled_market_does_not_keep_price_list_enabled(self):
		self.market.enabled = 0
		self.market.save()
		self.save_price_list(enabled=0)

	def test_shipping_setting_repair_does_not_validate_currency_or_tax(self):
		allow_multi_currency_invoices(self, 0)
		settings = frappe.get_doc("Commera Settings")
		settings.shipping_rule = "not-used"
		settings._doc_before_save = frappe.get_doc("Commera Settings")
		settings._doc_before_save.shipping_rule = "old-rule"
		with (
			patch.object(MarketStoreFit, "validate_invoice_currency", side_effect=AssertionError),
			patch.object(MarketStoreFit, "validate_tax_template", side_effect=AssertionError),
			patch("commera.localization.market_setup.has_delivery_services", return_value=True),
		):
			validate_markets_for_store(settings)

	def test_party_group_and_company_receivable_currency_routes(self):
		from commera.core import get_default_customer_group
		from commera.localization.market_setup import get_receivable_currencies

		allow_multi_currency_invoices(self, 0)
		company = frappe.db.get_single_value("Commera Settings", "company")
		account = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": "zz-market-currency",
				"company": company,
				"account_currency": self.market.currency,
			}
		)
		account.name = "zz-market-currency"
		account.db_insert()
		self.addCleanup(frappe.db.delete, "Account", account.name)
		group = get_default_customer_group()
		row = frappe.get_doc(
			{
				"doctype": "Party Account",
				"parenttype": "Customer Group",
				"parentfield": "accounts",
				"parent": group,
				"company": company,
				"account": account.name,
			}
		)
		row.db_insert()
		self.addCleanup(frappe.db.delete, "Party Account", row.name)
		self.assertIn(self.market.currency, get_receivable_currencies(company))
		MarketStoreFit(self.market).validate_invoice_currency()
		frappe.db.delete("Party Account", row.name)
		previous = frappe.db.get_value("Company", company, "default_receivable_account")
		self.addCleanup(frappe.db.set_value, "Company", company, "default_receivable_account", previous)
		frappe.db.set_value("Company", company, "default_receivable_account", account.name)
		frappe.clear_document_cache("Company", company)
		MarketStoreFit(self.market).validate_invoice_currency()

	def test_live_delivery_configuration_allows_a_country_outside_store_rule(self):
		with patch("commera.localization.market_setup.has_delivery_services", return_value=True):
			MarketStoreFit(self.market).validate_delivery_countries()
