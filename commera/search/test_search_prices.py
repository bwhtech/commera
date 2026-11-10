import copy
from contextlib import nullcontext
from unittest.mock import patch

import frappe
from frappe.utils import CallbackManager

from commera import utils
from commera.localization import pin_localization, resolve
from commera.localization.markets import CACHE_KEY as MARKETS_CACHE_KEY
from commera.search import query as search_query
from commera.search import sqlite_product_search, sync
from commera.search.engine_cache import clear_search_engine
from commera.search.sqlite_product_search import SqliteProductSearch
from commera.tests.test_market_prices import MarketPriceTestCase, make_price_list
from commera.tests.test_markets import make_market

TEST_INDEX_NAME = "test_commera_search_prices.db"
PRODUCT = "Style Attribute Variant"
TOKEN = "zzpricey"
SETTINGS_MODULE = "commera.commera_ecommerce.doctype.commera_settings.commera_settings"

# (sale, compare-at) per size. Store cards: other 50, discounted 70, unpriced 80, mixed 90 from 100.
# Gulf cards: discounted 200 from 400, mixed 250, other 260; unpriced has no Gulf price.
STORE_RATES = {
	"MIXED": {"M": (90, 100), "L": (None, 120)},
	"OTHER": {"M": (None, 50)},
	"DISCOUNTED": {"M": (None, 70)},
	"UNPRICED": {"M": (None, 80)},
}
GULF_RATES = {
	"MIXED": {"M": (300, 400), "L": (None, 250)},
	"OTHER": {"M": (260, None)},
	"DISCOUNTED": {"M": (200, 400)},
	"UNPRICED": {},
}


class SearchPriceTestCase(MarketPriceTestCase):
	"""Four products in a fixture-scoped index, priced in the store and in the Gulf market."""

	def setUp(self):
		super().setUp()
		self.swap_engine_attribute("INDEX_NAME", TEST_INDEX_NAME)
		self.addCleanup(lambda: SqliteProductSearch().drop_index())
		self.addCleanup(clear_search_engine)
		self.products, self.item_codes = {}, {}
		for label in STORE_RATES:
			self.products[label], self.item_codes[label] = self.make_product(label)
		self.mixed, self.other = self.products["MIXED"], self.products["OTHER"]
		self.discounted, self.unpriced = self.products["DISCOUNTED"], self.products["UNPRICED"]
		self.rebuild_index()

	def swap_engine_attribute(self, name, value):
		patcher = patch.object(SqliteProductSearch, name, value)
		patcher.start()
		self.addCleanup(patcher.stop)

	def make_product(self, label):
		item_codes = {size: self.make_item(f"{label}-{size}") for size in STORE_RATES[label]}
		for rates, (sale_list, compare_at_list) in (
			(STORE_RATES[label], (self.sale_price_list, self.default_price_list)),
			(GULF_RATES[label], (self.market_sale, self.market_compare_at)),
		):
			for size, (sale, compare_at) in rates.items():
				if sale is not None:
					self.make_item_price(item_codes[size], sale_list, sale)
				if compare_at is not None:
					self.make_item_price(item_codes[size], compare_at_list, compare_at)

		variant = self.make_variant(item_codes["M"], f"price-test-{label.lower()}-{self.suffix.lower()}")
		variant.display_name = f"{TOKEN.title()} {label.title()}"
		variant.sizes = []
		for size, item_code in item_codes.items():
			variant.append("sizes", {"size": size, "item_code": item_code})
		variant.save(ignore_permissions=True)
		return variant.name, item_codes

	def rebuild_index(self):
		scoped = copy.deepcopy(SqliteProductSearch.INDEXABLE_DOCTYPES)
		scoped[PRODUCT]["filters"] = {"is_published": 1, "name": ("in", list(self.products.values()))}
		scoped["Ecommerce Category"]["filters"] = {"enabled": 1, "name": ("in", ["-"])}
		self.swap_engine_attribute("INDEXABLE_DOCTYPES", scoped)
		with patch.object(frappe.db, "after_commit", CallbackManager()):
			SqliteProductSearch().drop_index()
			SqliteProductSearch().build_index()
		clear_search_engine()
		frappe.local.request_cache.clear()

	@property
	def engine(self):
		# A fresh engine per read: each memoizes the markets it prices.
		return SqliteProductSearch()

	def grid(self, sort_by="default", **filters):
		return self.engine.search_products({"search": TOKEN, **filters}, page_length=10, sort_by=sort_by)

	def count(self, **filters):
		return self.engine.search_count({"search": TOKEN, **filters})

	def cards(self, names):
		return {card["name"]: card for card in search_query.build_product_cards(names)}

	def qb_grid(self, sort_by="default", **filters):
		names = list(self.products.values())
		return [card["name"] for card in utils.get_product_list_qb(filters, names, sort_by=sort_by)]

	def in_each_market(self):
		return {"primary": nullcontext, "gulf": self.in_market}.items()

	def run_price_sync(self, change):
		"""Run `change` and commit it. Returns the products whose reindex it enqueued, now reindexed."""
		callbacks = CallbackManager()
		with (
			patch.object(frappe.db, "after_commit", callbacks),
			patch("commera.search.sync.frappe.enqueue") as enqueue,
		):
			change()
			callbacks.run()
		batches = [
			call.kwargs["names"]
			for call in enqueue.call_args_list
			if call.args == ("commera.search.sync.upsert_docs",)
		]
		for names in batches:
			sync.upsert_docs(PRODUCT, names)
		return batches

	def save_item_price(self, item_code, price_list, **changes):
		name = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": price_list})
		frappe.get_doc("Item Price", name).update(changes).save(ignore_permissions=True)


class TestSearchMarketPrices(SearchPriceTestCase):
	def test_a_secondary_market_sorts_by_its_card_prices(self):
		with self.in_market():
			self.assertEqual(self.grid("price_low"), [self.discounted, self.mixed, self.other])
			self.assertEqual(self.grid("price_high"), [self.other, self.mixed, self.discounted])
			self.assertEqual(self.grid("discount")[0], self.discounted)
			listed = utils.get_product_list({"search": TOKEN}, sort_by="price_low")
			self.assertEqual([card["name"] for card in listed], [self.discounted, self.mixed, self.other])

	def test_a_secondary_market_filters_by_its_card_prices(self):
		with self.in_market():
			# The mixed card sells at 250: its L size at compare-at, below its M on sale at 300.
			self.assertEqual(set(self.grid(max_price=251)), {self.discounted, self.mixed})
			self.assertEqual(self.grid(max_price=249), [self.discounted])
			self.assertEqual(set(self.grid(min_price=250)), {self.mixed, self.other})
			self.assertEqual(self.grid(min_price=251), [self.other])
			self.assertEqual(self.count(min_price=250, max_price=251), 1)
			self.assertEqual(self.grid(has_discount=1), [self.discounted])
			facets = self.engine.facet_counts({"search": TOKEN, "max_price": 251})
			self.assertEqual(facets["size"], {"M": 2, "L": 1})

	def test_results_show_the_market_card_prices(self):
		with self.in_market():
			cards = self.cards([self.mixed, self.discounted])
		mixed, discounted = cards[self.mixed], cards[self.discounted]
		self.assertEqual(
			(mixed["effective_price"], mixed["sale_price"], mixed["default_price"]), (250, None, None)
		)
		self.assertEqual((mixed["has_discount"], mixed["discount_percent"]), (0, 0))
		self.assertEqual((discounted["effective_price"], discounted["default_price"]), (200, 400))
		self.assertEqual((discounted["has_discount"], discounted["discount_percent"]), (1, 50))

	def test_a_product_without_a_market_price_is_left_out_of_that_market(self):
		with self.in_market():
			self.assertNotIn(self.unpriced, self.grid())
			self.assertEqual(self.count(), 3)
			self.assertNotIn(self.unpriced, self.engine.typeahead(TOKEN)["product_names"])
			self.assertEqual(self.engine.facet_counts({"search": TOKEN})["size"], {"M": 3, "L": 1})
		self.assertIn(self.unpriced, self.grid())
		self.assertEqual(self.count(), 4)
		self.assertIn(self.unpriced, self.engine.typeahead(TOKEN)["product_names"])

	def test_the_primary_market_matches_the_frappe_qb_grid(self):
		self.assertEqual(self.grid("price_low"), [self.other, self.discounted, self.unpriced, self.mixed])
		for sort_by in ("price_low", "price_high"):
			with self.subTest(sort_by=sort_by):
				self.assertEqual(self.grid(sort_by), self.qb_grid(sort_by))
		self.assertEqual(self.grid("discount")[0], self.qb_grid("discount")[0])
		for filters in ({"max_price": 75}, {"min_price": 75}, {"has_discount": 1}):
			with self.subTest(filters=filters):
				self.assertEqual(set(self.grid(**filters)), set(self.qb_grid(**filters)))
		index_card = self.cards([self.mixed])[self.mixed]
		qb_card = utils.get_product_list_qb(product_list=[self.mixed])[0]
		for column in ("effective_price", "sale_price", "default_price", "has_discount", "discount_percent"):
			self.assertEqual(index_card[column], qb_card[column], column)

	def test_the_gulf_grid_matches_the_frappe_qb_grid(self):
		with self.in_market():
			for sort_by in ("price_low", "price_high"):
				with self.subTest(sort_by=sort_by):
					expected = [name for name in self.qb_grid(sort_by) if name != self.unpriced]
					self.assertEqual(self.grid(sort_by), expected)

	def test_a_market_the_index_has_not_priced_is_served_by_frappe_qb(self):
		self.assertFalse(search_query.use_qb_fallback({"search": TOKEN}))
		sale = make_price_list("Saudi Sale", self.currency)
		make_market("Saudi", ["Saudi Arabia"], "en", handle="saudi", sale_price_list=sale)
		frappe.local.request_cache.clear()
		with pin_localization(resolve("/en-sa/")[0]):
			self.assertTrue(search_query.use_qb_fallback({"search": TOKEN}))
			self.rebuild_index()
			self.assertFalse(search_query.use_qb_fallback({"search": TOKEN}))
			self.assertEqual(self.grid(), [])


class TestSearchPriceSync(SearchPriceTestCase):
	def test_an_item_price_change_reindexes_its_products(self):
		batches = self.run_price_sync(
			lambda: self.save_item_price(
				self.item_codes["MIXED"]["L"], self.market_compare_at, price_list_rate=270
			)
		)
		self.assertEqual(batches, [[self.mixed]])
		with self.in_market():
			self.assertEqual(self.grid("price_low"), [self.discounted, self.other, self.mixed])
			self.assertEqual(self.cards([self.mixed])[self.mixed]["effective_price"], 270)

	def test_adding_and_deleting_a_market_price_adds_and_removes_the_product(self):
		item_code = self.item_codes["UNPRICED"]["M"]
		self.run_price_sync(lambda: self.make_item_price(item_code, self.market_sale, 230))
		with self.in_market():
			self.assertEqual(self.grid("price_low"), [self.discounted, self.unpriced, self.mixed, self.other])

		name = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": self.market_sale})
		self.run_price_sync(lambda: frappe.delete_doc("Item Price", name, ignore_permissions=True))
		with self.in_market():
			self.assertNotIn(self.unpriced, self.grid())

	def test_a_store_price_change_reindexes_the_primary_market(self):
		self.run_price_sync(
			lambda: self.save_item_price(
				self.item_codes["OTHER"]["M"], self.default_price_list, price_list_rate=95
			)
		)
		self.assertEqual(self.grid("price_low")[-1], self.other)

	def test_prices_outside_the_indexed_lists_reindex_nothing(self):
		other_list = make_price_list("Unindexed", self.currency)
		item_code = self.item_codes["MIXED"]["M"]
		self.assertEqual(self.run_price_sync(lambda: self.make_item_price(item_code, other_list, 10)), [])

		customer = frappe.db.get_value("Customer", {}, "name")
		if not customer:
			return
		price = frappe.new_doc("Item Price")
		price.update(
			{
				"item_code": item_code,
				"price_list": self.market_sale,
				"price_list_rate": 10,
				"customer": customer,
			}
		)
		self.assertEqual(self.run_price_sync(lambda: price.insert(ignore_permissions=True)), [])

	def test_a_market_price_list_change_rebuilds_the_index(self):
		cheaper = make_price_list("Gulf Cheaper", self.currency)
		self.make_item_price(self.item_codes["OTHER"]["M"], cheaper, 10)
		market = frappe.get_doc("Commera Market", "gulf")
		with patch("commera.search.price_sync.enqueue_full_rebuild") as rebuild:
			market.update({"compare_at_price_list": cheaper}).save(ignore_permissions=True)
		rebuild.assert_called_once_with(deduplicate=True)

		self.rebuild_index()
		# Without its compare-at rates, mixed sells at its M sale rate and nothing is crossed out.
		with self.in_market():
			self.assertEqual(self.grid("price_low"), [self.discounted, self.other, self.mixed])
			self.assertEqual(self.grid(has_discount=1), [])

	def test_enabling_or_deleting_a_market_rebuilds_the_index(self):
		market = frappe.get_doc("Commera Market", "gulf")
		for change in ({"enabled": 0}, {"enabled": 1}):
			with (
				self.subTest(change=change),
				patch("commera.search.price_sync.enqueue_full_rebuild") as rebuild,
			):
				market.update(change).save(ignore_permissions=True)
				rebuild.assert_called_once_with(deduplicate=True)
		with patch("commera.search.price_sync.enqueue_full_rebuild") as rebuild:
			market.update({"countries": [{"country": "Oman"}]}).save(ignore_permissions=True)
			rebuild.assert_not_called()
		with patch("commera.search.price_sync.enqueue_full_rebuild") as rebuild:
			frappe.delete_doc("Commera Market", "gulf", ignore_permissions=True)
			rebuild.assert_called_once_with(deduplicate=True)

	def test_a_store_price_list_change_rebuilds_the_index(self):
		before = frappe.get_doc("Commera Settings")
		settings = frappe.get_doc("Commera Settings")
		settings.sale_price_list = self.market_sale
		settings._doc_before_save = before
		with patch(f"{SETTINGS_MODULE}.enqueue_full_rebuild") as rebuild:
			settings.on_update()
		rebuild.assert_called_once_with(deduplicate=True)

	def test_a_market_change_during_a_build_rebuilds_again(self):
		callbacks = CallbackManager()
		with patch.object(frappe.db, "after_commit", callbacks):
			SqliteProductSearch().drop_index()
			SqliteProductSearch().build_index()
		frappe.db.set_value("Commera Market", "gulf", "enabled", 0)
		frappe.cache.delete_value(MARKETS_CACHE_KEY)
		with patch.object(SqliteProductSearch, "enqueue_full_rebuild") as rebuild:
			callbacks.run()
		rebuild.assert_called_once_with()

	def test_an_index_without_market_prices_counts_as_missing(self):
		self.engine.sql("DROP TABLE search_price", commit=True)
		self.assertFalse(self.engine.index_exists())
		with patch.object(sqlite_product_search.frappe, "enqueue") as enqueue:
			self.engine.ensure_index_built()
		enqueue.assert_called_once()
