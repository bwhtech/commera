"""Card prices per market for the search index. The store's prices are keyed SHOP_WIDE, like the
index's own rows; a secondary market with its own price lists is keyed by its handle."""

import frappe
from frappe.utils import create_batch, flt

from commera.base_prices import base_price_filters
from commera.card_prices import get_card_price
from commera.localization.content import SHOP_WIDE
from commera.localization.market_prices import MarketPrices
from commera.localization.markets import Market, StorefrontMarkets
from commera.localization.resolver import get_localization
from commera.utils import IN_CLAUSE_CHUNK_SIZE

# The card price columns each market row holds.
PRICE_COLUMNS = (
	"effective_price",
	"sale_price",
	"default_price",
	"discount_percent",
	"has_discount",
	"sale_end_date",
)


def get_price_markets(markets: StorefrontMarkets | None = None) -> dict[str, MarketPrices]:
	"""{key: prices} of each market the index prices: the store, and each enabled market with lists."""
	markets = markets or StorefrontMarkets.load()
	priced = {SHOP_WIDE: MarketPrices.of(markets.primary)}
	for market in markets.secondary:
		prices = MarketPrices.of(market)
		if not prices.uses_store_prices:
			priced[market.handle] = prices
	return priced


def get_price_market(market: Market | None = None) -> str:
	"""The key of the prices a search in `market` (default: this request's) sorts and shows."""
	market = market or get_localization().market
	return SHOP_WIDE if MarketPrices.of(market).uses_store_prices else market.handle


def price_generation(settings, markets: StorefrontMarkets | None = None) -> list:
	"""What decides the indexed prices: the store lists in `settings`, and each market's lists."""
	lists = [
		[key, prices.sale_price_list, prices.compare_at_price_list]
		for key, prices in get_price_markets(markets).items()
		if key != SHOP_WIDE
	]
	return [settings.sale_price_list, settings.default_price_list, lists]


def prices_for_variants(names, sizes_by_variant) -> dict[str, dict[str, dict]]:
	"""{variant: {market key: card prices}}. Every variant has store prices, 0 when unpriced, as
	before. A secondary market leaves out each variant it cannot price: it does not sell it."""
	price_markets = get_price_markets()
	codes_by_variant = {
		name: [size["item_code"] for size in sizes_by_variant.get(name, []) if size.get("item_code")]
		for name in names
	}
	codes = list({code for item_codes in codes_by_variant.values() for code in item_codes})
	price_lists = {name for prices in price_markets.values() for name in prices.price_lists}
	rates = rates_by_price_list(codes, sorted(price_lists))

	snapshots = {}
	for name, item_codes in codes_by_variant.items():
		by_market = snapshots[name] = {}
		for key, prices in price_markets.items():
			sale = rates.get(prices.sale_price_list, empty_rates())
			compare_at = rates.get(prices.compare_at_price_list, empty_rates())
			snapshot = aggregate_prices(item_codes, compare_at["rate"], sale["rate"], sale["upto"])
			if key == SHOP_WIDE:
				snapshot["effective_price"] = flt(snapshot["effective_price"])
			if snapshot["effective_price"] is not None:
				by_market[key] = snapshot
	return snapshots


def rates_by_price_list(item_codes, price_lists) -> dict[str, dict]:
	"""{price list: {rate: {item_code: min rate}, upto: {item_code: max valid_upto}}}."""
	rates = {}
	if not price_lists:
		return rates
	for chunk in create_batch(item_codes, IN_CLAUSE_CHUNK_SIZE):
		for row in frappe.get_all(
			"Item Price",
			filters=base_price_filters({"item_code": ("in", chunk), "price_list": ("in", price_lists)}),
			fields=["item_code", "price_list", "price_list_rate", "valid_upto"],
		):
			if row.price_list_rate is None:
				continue
			price_list = rates.setdefault(row.price_list, empty_rates())
			price_list["rate"][row.item_code] = min_or(
				price_list["rate"].get(row.item_code), row.price_list_rate
			)
			if row.valid_upto:
				price_list["upto"][row.item_code] = max_or(
					price_list["upto"].get(row.item_code), row.valid_upto
				)
	return rates


def rates_by_item_code(item_codes, default_price_list, sale_price_list):
	"""Per item_code: min default rate, min sale rate, max sale valid_upto across Item Price rows."""
	price_lists = [name for name in (default_price_list, sale_price_list) if name]
	rates = rates_by_price_list(item_codes, price_lists)
	default = rates.get(default_price_list, empty_rates())
	sale = rates.get(sale_price_list, empty_rates())
	return default["rate"], sale["rate"], sale["upto"]


def aggregate_prices(item_codes, default_rate, sale_rate, sale_upto):
	"""A product's card prices over its sizes (card_prices.get_card_price), with its last sale end."""
	upto_values = [sale_upto[code] for code in item_codes if code in sale_upto]
	return {
		**get_card_price([(sale_rate.get(code), default_rate.get(code)) for code in item_codes]),
		"sale_end_date": max(upto_values) if upto_values else None,
	}


def empty_rates():
	return {"rate": {}, "upto": {}}


def min_or(current, value):
	return value if current is None else min(current, value)


def max_or(current, value):
	return value if current is None else max(current, value)
