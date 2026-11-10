from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.storefront import products as products_api
from commera.localization import formatter as formatter_module
from commera.localization import pin_localization, resolve
from commera.localization.formatter import Formatter
from commera.localization.languages import Language
from commera.sdk import cart as cart_sdk
from commera.sdk import catalog
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_markets import UAE, make_market, use_markets
from commera.tests.test_product_details import ProductDetailPriceTestCase
from commera.utils import get_currency_symbol, get_product_list_qb

MARKET_CURRENCY = "AED"


def make_price_list(name, currency, selling=1):
	price_list = frappe.new_doc("Price List")
	price_list.price_list_name = f"{name} {frappe.generate_hash(length=6)}"
	price_list.currency = currency
	price_list.selling = selling
	price_list.buying = 0 if selling else 1
	price_list.enabled = 1
	return price_list.insert(ignore_permissions=True).name


def get_other_currency():
	store_currency = frappe.defaults.get_global_default("currency")
	return "EUR" if store_currency == MARKET_CURRENCY else MARKET_CURRENCY


class TestMarketPriceLists(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		use_markets(self)
		self.currency = get_other_currency()
		self.sale = make_price_list("Gulf Sale", self.currency)

	def test_the_market_currency_is_the_sale_price_list_currency(self):
		compare_at = make_price_list("Gulf Compare", self.currency)
		market = make_market("Gulf", [UAE], "ar", sale_price_list=self.sale, compare_at_price_list=compare_at)

		self.assertEqual(market.currency, self.currency)
		self.assertEqual(resolve("/ar-ae/")[0].market.currency, self.currency)
		self.assertEqual(resolve("/ar-ae/")[0].as_dict()["market"]["currency"], self.currency)

	def test_both_price_lists_must_share_one_currency(self):
		compare_at = make_price_list("Gulf Compare", frappe.defaults.get_global_default("currency"))

		with self.assertRaisesRegex(frappe.ValidationError, "Use one currency"):
			make_market("Gulf", [UAE], "ar", sale_price_list=self.sale, compare_at_price_list=compare_at)

	def test_a_market_price_list_must_be_a_selling_list(self):
		buying = make_price_list("Gulf Buying", self.currency, selling=0)

		with self.assertRaisesRegex(frappe.ValidationError, "not a selling price list"):
			make_market("Gulf", [UAE], "ar", sale_price_list=buying)

	def test_the_currency_of_a_market_price_list_cannot_change(self):
		make_market("Gulf", [UAE], "ar", sale_price_list=self.sale)
		price_list = frappe.get_doc("Price List", self.sale)

		price_list.currency = frappe.defaults.get_global_default("currency")
		with self.assertRaisesRegex(frappe.ValidationError, "currency cannot change"):
			price_list.save()


class MarketPriceTestCase(ProductDetailPriceTestCase):
	"""The store sells in its own currency. The Gulf market sells in its own price lists."""

	def setUp(self):
		super().setUp()
		use_storefront_languages(self, "en", published=("en", "ar"))
		use_markets(self)
		self.addCleanup(frappe.local.request_cache.clear)
		self.currency = get_other_currency()
		self.market_sale = make_price_list("Gulf Sale", self.currency)
		self.market_compare_at = make_price_list("Gulf Compare", self.currency)
		make_market(
			"Gulf",
			[UAE],
			"ar",
			["en"],
			handle="gulf",
			sale_price_list=self.market_sale,
			compare_at_price_list=self.market_compare_at,
		)
		self.store_currency = frappe.defaults.get_global_default("currency")

	def make_item(self, label):
		# Not stock-tracked, so stock never decides availability here.
		item_code = super().make_item(label)
		frappe.db.set_value("Item", item_code, "is_stock_item", 0)
		return item_code

	def make_market_variant(self, label, market_sale=None, market_compare_at=None):
		"""A product priced 100 / 80 in the store, and at the given rates in the Gulf market."""
		route = self.make_priced_variant(label, default_rate=100, sale_rate=80)
		item_code = self.get_item_code(route)
		if market_compare_at is not None:
			self.make_item_price(item_code, self.market_compare_at, market_compare_at)
		if market_sale is not None:
			self.make_item_price(item_code, self.market_sale, market_sale)
		return route

	def get_item_code(self, route):
		variant = frappe.db.get_value("Style Attribute Variant", {"route": route})
		return frappe.db.get_value("Color Size Item", {"parent": variant}, "item_code")

	def in_market(self):
		return pin_localization(resolve("/en-ae/")[0])

	def get_card(self, route):
		cards = catalog.get_product_cards_for(
			[frappe.db.get_value("Style Attribute Variant", {"route": route})]
		)
		return cards[0]

	def list_only(self, names):
		"""The grid's own frappe.qb query over this test's products: other products share the site."""

		def get_product_list(filters=None, **kwargs):
			return get_product_list_qb(filters, product_list=list(names), page_length=len(names))

		return get_product_list


class TestMarketProductPrices(MarketPriceTestCase):
	def test_the_primary_market_keeps_the_store_prices(self):
		route = self.make_market_variant("PRIMARY", market_sale=300, market_compare_at=400)

		product = catalog.get_product(route)
		card = self.get_card(route)

		self.assertEqual((product["currency"], product["price"]), (self.store_currency, 80))
		self.assertEqual(product["variants"][0]["compare_at_price"], 100)
		self.assertEqual(
			(card["currency"], card["price"], card["compare_at_price"]), (self.store_currency, 80, 100)
		)
		self.assertTrue(card["available"])

	def test_a_secondary_market_shows_its_own_prices_and_currency(self):
		route = self.make_market_variant("GULF", market_sale=300, market_compare_at=400)

		with self.in_market():
			product = catalog.get_product(route)
			card = self.get_card(route)

		variant = product["variants"][0]
		self.assertEqual((product["currency"], product["price"]), (self.currency, 300))
		self.assertEqual((variant["price"], variant["compare_at_price"]), (300, 400))
		self.assertTrue(product["available"] and variant["available"])
		self.assertEqual(
			(card["currency"], card["price"], card["compare_at_price"]), (self.currency, 300, 400)
		)
		self.assertTrue(card["available"])

	def test_a_compare_at_price_shows_only_above_the_sale_price(self):
		route = self.make_market_variant("NOSALE", market_sale=300, market_compare_at=300)

		with self.in_market():
			variant = catalog.get_product(route)["variants"][0]
			card = self.get_card(route)

		self.assertIsNone(variant["compare_at_price"])
		self.assertIsNone(card["compare_at_price"])

	def test_an_item_priced_only_in_the_compare_at_list_sells_at_that_rate(self):
		# Like the primary market: the compare-at rate is then the full price, not crossed out.
		route = self.make_market_variant("FULLPRICE", market_compare_at=400)
		item_code = self.get_item_code(route)

		with self.in_market():
			product = catalog.get_product(route)
			card = self.get_card(route)
			item = catalog.get_items([item_code])[item_code]
			cart_sdk.validate_items_for_sale([{"item_code": item_code, "qty": 1}])

		variant = product["variants"][0]
		self.assertEqual(
			(variant["price"], variant["compare_at_price"], variant["available"]), (400, None, True)
		)
		self.assertEqual((product["price"], product["available"]), (400, True))
		self.assertEqual((card["price"], card["compare_at_price"], card["available"]), (400, None, True))
		self.assertEqual(item["price"], 400)

	def test_an_item_in_neither_market_list_is_unavailable(self):
		route = self.make_market_variant("UNPRICED")

		with self.in_market():
			product = catalog.get_product(route)
			card = self.get_card(route)
			items = catalog.get_items([self.get_item_code(route)])

		variant = product["variants"][0]
		self.assertEqual((variant["price"], variant["available"]), (None, False))
		self.assertEqual((product["price"], product["available"]), (None, False))
		self.assertEqual((card["price"], card["compare_at_price"], card["available"]), (None, None, False))
		self.assertIsNone(items[self.get_item_code(route)]["price"])

	def test_catalog_items_carry_the_market_price_and_currency(self):
		route = self.make_market_variant("ITEMS", market_sale=300, market_compare_at=400)
		item_code = self.get_item_code(route)

		with self.in_market():
			item = catalog.get_items([item_code])[item_code]

		self.assertEqual((item["price"], item["list_price"], item["currency"]), (300, 400, self.currency))
		self.assertEqual(catalog.get_items([item_code])[item_code]["price"], 80)

	def test_money_formats_in_the_market_currency(self):
		route = self.make_market_variant("MONEY", market_sale=1250)
		with self.in_market():
			product = catalog.get_product(route)

		# The CI site uses the Indian number format.
		english = Language("en", "English", "English", "ltr")
		with patch.object(formatter_module, "get_money_precision", lambda currency: 2):
			money = Formatter(english, "#,###.##").money(product["price"], product["currency"])
		self.assertEqual(money, f"{get_currency_symbol(self.currency)}1,250.00")


class TestMarketProductListing(MarketPriceTestCase):
	def test_the_listing_shows_market_prices_and_unpriced_products_as_unavailable(self):
		priced = self.make_market_variant("LISTPRICED", market_sale=300, market_compare_at=400)
		unpriced = self.make_market_variant("LISTUNPRICED")
		names = {
			frappe.db.get_value("Style Attribute Variant", {"route": route}): route
			for route in (priced, unpriced)
		}

		with self.in_market(), patch.object(catalog, "get_product_list", self.list_only(names)):
			page = catalog.list_products()

		cards = {card["handle"]: card for card in page["products"]}
		self.assertEqual((cards[priced]["price"], cards[priced]["currency"]), (300, self.currency))
		self.assertTrue(cards[priced]["available"])
		self.assertEqual((cards[unpriced]["price"], cards[unpriced]["available"]), (None, False))
		self.assertEqual(page["facets"]["price"], {"min": 300, "max": 300, "currency": self.currency})

	def test_filters_sorting_and_the_facet_use_the_compare_at_rate_without_a_sale_rate(self):
		on_sale = self.make_market_variant("ONSALE", market_sale=300, market_compare_at=400)
		full_price = self.make_market_variant("FULL", market_compare_at=250)
		unpriced = self.make_market_variant("NONE")
		names = [
			frappe.db.get_value("Style Attribute Variant", {"route": route})
			for route in (on_sale, full_price)
		]
		all_names = [*names, frappe.db.get_value("Style Attribute Variant", {"route": unpriced})]

		with self.in_market():
			cheapest_first = get_product_list_qb(product_list=names, page_length=2, sort_by="price_low")
			above = get_product_list_qb({"min_price": 260}, product_list=all_names, page_length=3)
			below = get_product_list_qb({"max_price": 260}, product_list=all_names, page_length=3)
			facet = catalog.get_market_price_facet()

		self.assertEqual([card["route"] for card in cheapest_first], [full_price, on_sale])
		self.assertEqual([card["route"] for card in above], [on_sale])
		self.assertEqual([card["route"] for card in below], [full_price])
		self.assertEqual((facet["min"], facet["max"]), (250, 300))

	def test_the_price_facet_is_cached_per_market(self):
		self.make_market_variant("FACET", market_sale=300)

		with self.in_market():
			market_facet = catalog.get_price_facet(self.market_sale)
		store_facet = catalog.get_price_facet(self.sale_price_list)

		self.assertEqual(market_facet, {"min": 300, "max": 300})
		self.assertEqual(store_facet, {"min": 80, "max": 80})


class TestMarketStorefrontApi(MarketPriceTestCase):
	def setUp(self):
		super().setUp()
		# Every direct call shares one rate-limit counter for this IP, and it outlives the test.
		frappe.cache.delete_keys("rl:*127.0.0.1*")
		frappe.local.request_ip = "127.0.0.1"

	def send(self, **form):
		frappe.local.form_dict = frappe._dict(form)
		frappe.local.request_cache.clear()

	def test_the_product_endpoint_prices_the_market_of_country(self):
		route = self.make_market_variant("APIPRODUCT", market_sale=300, market_compare_at=400)

		self.send(_country="AE")
		in_market = products_api.get_product(route)
		self.send()
		in_store = products_api.get_product(route)

		self.assertEqual((in_market["price"], in_market["currency"]), (300, self.currency))
		self.assertEqual((in_store["price"], in_store["currency"]), (80, self.store_currency))

	def test_the_list_endpoint_prices_the_market_of_country(self):
		route = self.make_market_variant("APILIST", market_sale=300)
		name = frappe.db.get_value("Style Attribute Variant", {"route": route})

		self.send(_country="AE")
		with patch.object(catalog, "get_product_list", self.list_only([name])):
			page = products_api.get_products()

		self.assertEqual(
			[(card["price"], card["currency"]) for card in page["products"]], [(300, self.currency)]
		)


class TestMarketCart(MarketPriceTestCase):
	def test_an_item_in_neither_market_list_cannot_be_added_to_the_cart(self):
		unpriced = self.get_item_code(self.make_market_variant("CARTUNPRICED"))

		with self.in_market(), self.assertRaisesRegex(frappe.ValidationError, "not available in this market"):
			cart_sdk.validate_items_for_sale([{"item_code": unpriced, "qty": 1}])

	def test_a_priced_item_passes_and_the_primary_market_is_unchanged(self):
		priced = self.get_item_code(self.make_market_variant("CARTPRICED", market_sale=300))
		unpriced = self.get_item_code(self.make_market_variant("CARTSTORE"))

		with self.in_market():
			cart_sdk.validate_items_for_sale([{"item_code": priced, "qty": 1}])
		cart_sdk.validate_items_for_sale([{"item_code": unpriced, "qty": 1}])
