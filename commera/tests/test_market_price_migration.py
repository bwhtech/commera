import os
from unittest.mock import patch

import frappe
from frappe.utils import get_files_path

from commera import seo
from commera.commera_ecommerce.doctype.commera_market.commera_market import validate_market_price_list
from commera.localization import formatter as formatter_module
from commera.localization import markets as markets_module
from commera.localization import pin_localization, resolve
from commera.localization.formatter import Formatter
from commera.localization.languages import Language
from commera.localization.market_prices import MarketPrices
from commera.og import generator
from commera.patches import set_market_price_lists
from commera.sdk import cart as cart_sdk
from commera.sdk import catalog
from commera.tests.test_market_prices import MarketPriceTestCase, make_price_list
from commera.tests.test_markets import make_market
from commera.themes.commera_starter.pages.products import details as starter_details
from commera.themes.commera_starter.pages.products import list as starter_list
from commera.utils import get_currency_symbol
from commera.www import og_image_render


class TestMarketPriceBackfill(MarketPriceTestCase):
	def make_unpriced_market(self, name, country):
		market = make_market(name, [country], "ar", sale_price_list=self.market_sale)
		empty = {"sale_price_list": None, "compare_at_price_list": None, "currency": None}
		frappe.db.set_value("Commera Market", market.name, empty, update_modified=False)
		return market.name

	def set_store_lists(self, default, sale):
		frappe.db.set_single_value(
			"Commera Settings", {"default_price_list": default, "sale_price_list": sale}
		)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

	def get_lists(self, market):
		fields = ["sale_price_list", "compare_at_price_list", "currency"]
		return tuple(frappe.db.get_value("Commera Market", market, fields))

	def test_a_market_gets_the_store_lists_once(self):
		market = self.make_unpriced_market("Backfill", "Qatar")
		own = self.make_unpriced_market("Own Lists", "Oman")
		frappe.db.set_value("Commera Market", own, "sale_price_list", self.market_sale)

		set_market_price_lists.execute()
		filled = self.get_lists(market)
		set_market_price_lists.execute()

		expected = (self.sale_price_list, self.default_price_list, self.store_currency)
		self.assertEqual(filled, expected)
		self.assertEqual(self.get_lists(market), expected)
		self.assertEqual(self.get_lists(own)[0], self.market_sale)

	def test_a_store_with_only_a_default_list_sells_at_it(self):
		market = self.make_unpriced_market("Default Only", "Qatar")
		self.set_store_lists(self.default_price_list, None)

		set_market_price_lists.execute()

		self.assertEqual(self.get_lists(market), (self.default_price_list, None, self.store_currency))

	def test_a_market_without_store_lists_is_logged_and_keeps_store_prices(self):
		market = self.make_unpriced_market("No Lists", "Qatar")
		self.set_store_lists(None, None)
		with patch.object(frappe, "log_error") as log_error:
			set_market_price_lists.execute()

		self.assertEqual(self.get_lists(market), (None, None, None))
		titles = [call.kwargs["title"] for call in log_error.call_args_list]
		self.assertEqual(titles, [f"Commera Market {market} has no sale price list"])
		markets_module.clear_market_cache()
		self.assertTrue(MarketPrices.of(resolve("/ar-qa/")[0].market).uses_store_prices)

	def test_a_sparse_store_sale_list_keeps_prices_and_availability(self):
		# The store's sale list holds only discounted items: this one sells at its default rate.
		route = self.make_priced_variant("SPARSE", default_rate=100)
		frappe.db.set_value("Item", self.get_item_code(route), "is_stock_item", 0)
		self.make_unpriced_market("Sparse", "Qatar")
		markets_module.clear_market_cache()
		before = self.read_in_qatar(route)

		set_market_price_lists.execute()

		self.assertEqual(before, (100, True, 100, True))
		self.assertEqual(self.read_in_qatar(route), before)
		with pin_localization(resolve("/ar-qa/")[0]):
			item_code = self.get_item_code(route)
			cart_sdk.validate_items_for_sale([{"item_code": item_code, "qty": 1}])

	def read_in_qatar(self, route):
		with pin_localization(resolve("/ar-qa/")[0]):
			product = catalog.get_product(route)
			card = self.get_card(route)
		return (product["price"], product["available"], card["price"], card["available"])


def without_price_columns(doctype, column, *args, **kwargs):
	return False if doctype == "Commera Market" and column in markets_module.PRICE_FIELDS else True


class TestBeforeSchemaSync(MarketPriceTestCase):
	def test_markets_load_without_the_price_columns_and_keep_store_prices(self):
		markets_module.clear_market_cache()
		self.addCleanup(markets_module.clear_market_cache)
		with patch.object(frappe.db, "has_column", side_effect=without_price_columns):
			market = resolve("/en-ae/")[0].market

		self.assertEqual((market.handle, market.sale_price_list), ("gulf", None))
		self.assertTrue(MarketPrices.of(market).uses_store_prices)

	def test_a_price_list_currency_change_skips_the_market_check(self):
		price_list = frappe.get_doc("Price List", self.market_sale)
		price_list.currency = self.store_currency

		with patch.object(frappe.db, "has_column", side_effect=without_price_columns):
			validate_market_price_list(price_list)
		with self.assertRaisesRegex(frappe.ValidationError, "currency cannot change"):
			validate_market_price_list(price_list)


class TestListingCurrency(MarketPriceTestCase):
	def test_the_price_facet_and_the_price_chip_use_the_market_currency(self):
		self.make_market_variant("CHIP", market_sale=300)
		english = Language("en", "English", "English", "ltr")
		# The CI site uses the Indian number format.
		with (
			self.in_market(),
			patch.object(Formatter, "current", return_value=Formatter(english, "#,###.##")),
			patch.object(formatter_module, "get_money_precision", lambda currency: 2),
		):
			facet = starter_list.catalog.get_market_price_facet()
			label = starter_list.get_price_label(frappe._dict(min=10, max=20), facet["currency"])

		symbol = get_currency_symbol(self.currency)
		self.assertEqual(facet["currency"], self.currency)
		self.assertEqual(label, f"{symbol}10.00 to {symbol}20.00")

	def test_the_price_inputs_format_in_the_facet_currency(self):
		path = os.path.join(frappe.get_app_path("commera"), "themes", "commera_starter", "components")
		with open(
			os.path.join(path, "product_grid.html")
		) as template:  # nosemgrep: frappe-security-file-traversal
			source = template.read()

		self.assertIn("money(facets.price.min, facets.price.currency)", source)
		self.assertIn("money(facets.price.max, facets.price.currency)", source)


class TestMarketOgCard(MarketPriceTestCase):
	def test_a_secondary_market_links_the_card_without_a_price(self):
		with self.in_market():
			market_url = starter_details.get_og_image_url("shirt")
			localized = seo.get_product_og_image("shirt")

		# The locale prefix keeps the card's text in the market; the flag drops its store price.
		self.assertEqual(market_url, f"{localized}?price=none")
		self.assertEqual(starter_details.get_og_image_url("shirt"), "/og-image/shirt.png")

	def test_the_card_without_a_price_shows_none(self):
		route = self.make_market_variant("OGCARD", market_sale=300)
		variant = frappe.get_doc("Style Attribute Variant", {"route": route})

		with patch.object(generator, "product_image_data_uri", return_value=None):
			priced = generator.build_variant_card_context(variant)
			unpriced = generator.build_variant_card_context(variant, with_price=False)

		self.assertIn("80.00", priced["price"])
		self.assertEqual(unpriced["price"], "")

	def test_the_card_without_a_price_has_its_own_cache_file(self):
		route = self.make_market_variant("OGCACHE", market_sale=300)
		cache_dir = os.path.join(get_files_path(is_private=False), og_image_render.CACHE_SUBDIR)
		version = generator.get_variant_card_version(
			frappe.get_doc("Style Attribute Variant", {"route": route})
		)
		priced_path = og_image_render.cache_file_path(route, version)
		unpriced_path = og_image_render.cache_file_path(f"{route}?price=none", version)
		for path in (priced_path, unpriced_path):
			self.addCleanup(lambda path=path: os.path.exists(path) and os.remove(path))

		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		frappe.local.form_dict = frappe._dict(route=f"{route}.png", price="none")
		with patch.object(og_image_render, "render_card_for_doc", return_value=b"png") as render:
			with self.assertRaises(frappe.Redirect):
				og_image_render.get_context(frappe._dict())

		self.assertNotEqual(priced_path, unpriced_path)
		self.assertTrue(unpriced_path.startswith(cache_dir) and os.path.exists(unpriced_path))
		self.assertFalse(os.path.exists(priced_path))
		self.assertEqual(render.call_args.kwargs, {"with_price": False})


class TestMarketCurrencyOfPriceLists(MarketPriceTestCase):
	def test_a_market_compare_at_list_in_another_currency_is_not_backfilled(self):
		other = make_price_list("Other Default", self.currency)
		frappe.db.set_single_value("Commera Settings", "default_price_list", other)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

		self.assertEqual(
			set_market_price_lists.get_store_price_lists(),
			{
				"sale_price_list": self.sale_price_list,
				"compare_at_price_list": None,
				"currency": self.store_currency,
			},
		)
