from contextlib import nullcontext
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from commera import card_prices
from commera.card_prices import get_card_price
from commera.sdk import catalog
from commera.search.facets import get_price_range
from commera.search.price_markets import aggregate_prices
from commera.tests.test_market_prices import MarketPriceTestCase
from commera.utils import get_product_count_qb, get_product_list_qb

# The reviewer's product: M on sale at 300 from 400, L at its compare-at rate of 250 only.
MIXED_SIZES = {"M": (300, 400), "L": (None, 250)}


class TestCardPriceRule(UnitTestCase):
	def test_the_card_shows_its_lowest_size_price(self):
		card = get_card_price(list(MIXED_SIZES.values()))

		self.assertEqual(
			(card["effective_price"], card["sale_price"], card["default_price"]), (250, None, None)
		)
		self.assertEqual((card["discount_percent"], card["has_discount"]), (0, 0))

	def test_the_compare_at_rate_of_the_cheapest_size_is_crossed_out(self):
		card = get_card_price([(300, 400), (None, 350)])

		self.assertEqual(
			(card["effective_price"], card["default_price"], card["has_discount"]), (300, 400, 1)
		)
		self.assertEqual(card["discount_percent"], 25)

	def test_a_half_percent_discount_is_not_lost_to_float_rounding(self):
		card = get_card_price([(42.5, 100)])
		self.assertEqual(card["discount_percent"], 57.5)

	def test_a_compare_at_rate_below_the_sale_rate_is_not_crossed_out(self):
		card = get_card_price([(300, 250)])

		self.assertEqual((card["effective_price"], card["default_price"]), (300, None))
		self.assertEqual((card["discount_percent"], card["has_discount"]), (0, 0))

	def test_a_product_with_no_priced_size_has_no_price(self):
		self.assertIsNone(get_card_price([(None, None)])["effective_price"])

	def test_the_index_snapshot_uses_the_same_rule(self):
		snapshot = aggregate_prices(["M", "L"], {"M": 400, "L": 250}, {"M": 300}, {})

		self.assertEqual((snapshot["effective_price"], snapshot["default_price"]), (250, None))


class CardPriceTestCase(MarketPriceTestCase):
	"""Each product has the same rates in the store lists and in the Gulf market lists."""

	def make_product(self, label, rates_by_size):
		item_codes = {size: self.make_item(f"{label}-{size}") for size in rates_by_size}
		for size, (sale, compare_at) in rates_by_size.items():
			for sale_list, compare_at_list in (
				(self.sale_price_list, self.default_price_list),
				(self.market_sale, self.market_compare_at),
			):
				if sale is not None:
					self.make_item_price(item_codes[size], sale_list, sale)
				if compare_at is not None:
					self.make_item_price(item_codes[size], compare_at_list, compare_at)

		variant = self.make_variant(item_codes["M"], f"card-test-{label.lower()}-{self.suffix.lower()}")
		variant.sizes = []
		for size, item_code in item_codes.items():
			variant.append("sizes", {"size": size, "item_code": item_code})
		variant.save(ignore_permissions=True)
		return variant.name, item_codes

	def in_each_market(self):
		return {"primary": nullcontext, "gulf": self.in_market}.items()

	def grid(self, names, filters=None, sort_by="default"):
		return [card["name"] for card in get_product_list_qb(filters, names, page_length=10, sort_by=sort_by)]


class TestMarketCardPrices(CardPriceTestCase):
	def test_the_card_filters_sort_and_facet_agree_on_the_lowest_size_price(self):
		mixed, _item_codes = self.make_product("MIXED", MIXED_SIZES)
		other, _item_codes = self.make_product("OTHER", {"M": (260, None)})
		names = [mixed, other]

		for market, context in self.in_each_market():
			with self.subTest(market=market), context():
				card = catalog.get_product_cards_for([mixed])[0]
				self.assertEqual((card["price"], card["compare_at_price"]), (250, None))
				self.assertEqual(get_product_list_qb(product_list=[mixed])[0]["effective_price"], 250)

				self.assertEqual(self.grid(names, {"max_price": 251}), [mixed])
				self.assertEqual(self.grid(names, {"max_price": 249}), [])
				self.assertEqual(sorted(self.grid(names, {"min_price": 250})), sorted(names))
				self.assertEqual(self.grid(names, {"min_price": 251}), [other])
				self.assertEqual(get_product_count_qb({"min_price": 251}, names), 1)
				self.assertEqual(self.grid(names, sort_by="price_low"), [mixed, other])
				self.assertEqual(self.grid(names, sort_by="price_high"), [other, mixed])

	def test_the_price_facet_spans_the_card_prices(self):
		self.make_product("FACETMIXED", MIXED_SIZES)
		self.make_product("FACETOTHER", {"M": (260, None)})

		self.assertEqual(
			get_price_range(self.sale_price_list, self.default_price_list),
			{"min_price": 250, "max_price": 260},
		)
		self.assertEqual(
			get_price_range(self.market_sale, self.market_compare_at), {"min_price": 250, "max_price": 260}
		)

	def test_a_size_filter_does_not_change_the_card_price(self):
		mixed, _item_codes = self.make_product("SIZEFILTER", MIXED_SIZES)

		for market, context in self.in_each_market():
			with self.subTest(market=market), context():
				cards = get_product_list_qb({"sizes": ["M"]}, [mixed])
				self.assertEqual((cards[0]["effective_price"], cards[0]["default_price"]), (250, None))

	def test_on_sale_lists_only_cards_with_a_crossed_out_price(self):
		mixed, _item_codes = self.make_product("SALEMIXED", MIXED_SIZES)
		discounted, _item_codes = self.make_product("SALEDISCOUNTED", {"M": (200, 400)})

		for market, context in self.in_each_market():
			with self.subTest(market=market), context():
				self.assertEqual(self.grid([mixed, discounted], {"has_discount": True}), [discounted])
				self.assertEqual(self.grid([mixed, discounted], sort_by="discount"), [discounted, mixed])

	def test_a_card_never_crosses_out_a_price_below_its_price(self):
		name, _item_codes = self.make_product("BELOW", {"M": (300, 250)})

		for market, context in self.in_each_market():
			with self.subTest(market=market), context():
				card = catalog.get_product_cards_for([name])[0]
				row = get_product_list_qb(product_list=[name])[0]
				self.assertEqual((card["price"], card["compare_at_price"]), (300, None))
				self.assertEqual((row["has_discount"], row["discount_percent"]), (0, 0))

	def test_catalog_items_cross_out_only_a_sale_rate(self):
		_name, item_codes = self.make_product("ITEMS", {**MIXED_SIZES, "S": (300, 250)})
		codes = list(item_codes.values())

		for market, context in self.in_each_market():
			with self.subTest(market=market), context():
				items = catalog.get_items(codes)
				prices = {
					size: (items[code]["price"], items[code]["list_price"])
					for size, code in item_codes.items()
				}
				self.assertEqual(prices, {"M": (300, 400), "L": (250, None), "S": (300, None)})
				currency = self.currency if market == "gulf" else self.store_currency
				self.assertEqual({item["currency"] for item in items.values()}, {currency})


class TestCardPriceQueryScope(CardPriceTestCase):
	"""The card prices are built for the grid's candidate products, never the whole shop."""

	def test_a_one_product_list_prices_only_that_product(self):
		mixed, _item_codes = self.make_product("ONE", MIXED_SIZES)
		self.make_product("ONEOTHER", {"M": (260, None)})

		for sort_by in ("default", "price_low"):
			with self.subTest(sort_by=sort_by):
				cards, candidates = card_price_candidates(
					lambda sort_by=sort_by: get_product_list_qb(product_list=[mixed], sort_by=sort_by)
				)
				self.assertEqual(candidates, [[mixed]])
				self.assertEqual(cards[0]["effective_price"], 250)

	def test_a_page_is_priced_after_it_is_picked(self):
		names = [self.make_product(label, MIXED_SIZES)[0] for label in ("PAGEA", "PAGEB")]

		cards, candidates = card_price_candidates(
			lambda: get_product_list_qb(product_list=names, page_length=1)
		)
		self.assertEqual(candidates, [[cards[0]["name"]]])

	def test_a_price_filter_prices_only_the_filtered_products(self):
		mixed, _item_codes = self.make_product("FILTERED", MIXED_SIZES)
		self.make_product("FILTEREDOTHER", {"M": (260, None)})
		in_group = {"subcategory": [self.item_group]}
		priced = {**in_group, "max_price": 251}

		cards, (candidates,) = card_price_candidates(lambda: get_product_list_qb(priced))
		self.assertEqual([card["name"] for card in cards], [mixed])
		self.assertIn(self.item_group, str(candidates))
		count, (candidates,) = card_price_candidates(lambda: get_product_count_qb(priced))
		self.assertEqual(count, 1)
		self.assertIn(self.item_group, str(candidates))
		self.assertEqual(card_price_candidates(lambda: get_product_count_qb(in_group)), (2, []))


def card_price_candidates(run):
	"""`run`'s result, and the candidate products each card-price query was built for."""
	calls = []
	build = card_prices.card_prices_query

	def record(sale_price_list, compare_at_price_list, products):
		calls.append(products)
		return build(sale_price_list, compare_at_price_list, products)

	with patch.object(card_prices, "card_prices_query", record):
		result = run()
	return result, calls
