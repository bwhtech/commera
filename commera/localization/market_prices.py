"""The prices of the request's market, from its own price lists. Commera converts no currency, so a
secondary market sells only items with a price in its sale price list."""

from dataclasses import dataclass

import frappe
from frappe.utils.data import flt

from commera.base_prices import base_price_filters
from commera.localization.markets import Market
from commera.localization.resolver import get_localization
from commera.utils import get_store_currency


@dataclass(frozen=True)
class MarketPrices:
	# The store's lists and currency: the primary market, or a market with no lists of its own.
	uses_store_prices: bool
	sale_price_list: str | None
	compare_at_price_list: str | None
	currency: str

	@classmethod
	def current(cls) -> "MarketPrices":
		return cls.of(get_localization().market)

	@classmethod
	def of(cls, market: Market | None) -> "MarketPrices":
		"""Store lists are read here: a cached localization may predate them. A market without a sale
		list (before the schema sync, or one the backfill could not fill) keeps the store prices."""
		if market and not market.is_primary and market.sale_price_list:
			return cls(False, market.sale_price_list, market.compare_at_price_list, market.currency)
		settings = frappe.get_cached_doc("Commera Settings")
		return cls(True, settings.sale_price_list, settings.default_price_list, get_store_currency())

	@property
	def cache_key(self) -> str:
		"""Part of the key of any cache that holds prices or filters by them."""
		return f"{self.sale_price_list}|{self.compare_at_price_list}"

	def price(self, sale: float | None, compare_at: float | None) -> float | None:
		"""What a shopper pays, or None when the item is not for sale in this market.
		Store prices fall back to the compare-at price, as the store always did."""
		if sale is not None:
			return flt(sale)
		return flt(compare_at) if self.uses_store_prices else None

	def compare_at(self, price: float | None, compare_at: float | None) -> float | None:
		"""The struck-through price: only above the price paid."""
		if price is None or not compare_at or flt(compare_at) <= price:
			return None
		return flt(compare_at)

	def get_unpriced(self, item_codes: list[str]) -> set[str]:
		"""The items this market cannot sell: those with no price in its sale price list."""
		if self.uses_store_prices or not item_codes:
			return set()
		priced = frappe.get_all(
			"Item Price",
			filters=base_price_filters(
				{"item_code": ("in", item_codes), "price_list": self.sale_price_list or ""}
			),
			pluck="item_code",
		)
		return set(item_codes) - set(priced)
