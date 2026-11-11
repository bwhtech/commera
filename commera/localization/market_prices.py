"""The prices of the request's market, from its own price lists. Commera converts no currency, so a
secondary market sells only items with a price in its sale or compare-at price list."""

from dataclasses import dataclass

import frappe
from frappe.utils.data import flt

from commera.api.variant_pricing import get_base_price_rows_by_key
from commera.localization.markets import PRIMARY_MARKET, Market
from commera.localization.resolver import get_localization
from commera.utils import get_store_currency


@dataclass(frozen=True)
class MarketPrices:
	# The handle of the market priced in. Lists and currency alone may match another market's.
	handle: str
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
			return cls(
				market.handle, False, market.sale_price_list, market.compare_at_price_list, market.currency
			)
		settings = frappe.get_cached_doc("Commera Settings")
		handle = market.handle if market else PRIMARY_MARKET
		return cls(handle, True, settings.sale_price_list, settings.default_price_list, get_store_currency())

	@property
	def cache_key(self) -> str:
		"""Part of the key of any cache that holds prices or filters by them."""
		return f"{self.sale_price_list}|{self.compare_at_price_list}"

	def price(self, sale: float | None, compare_at: float | None) -> float | None:
		"""The sale rate, else the compare-at rate as the full price. None when neither list prices the
		item: not for sale in a secondary market. The store prices that as 0, as it always did."""
		if sale is not None:
			return flt(sale)
		if compare_at is not None or self.uses_store_prices:
			return flt(compare_at)
		return None

	def compare_at(self, price: float | None, compare_at: float | None) -> float | None:
		"""The struck-through price: only above the price paid."""
		if price is None or not compare_at or flt(compare_at) <= price:
			return None
		return flt(compare_at)

	@property
	def price_lists(self) -> list[str]:
		return [name for name in (self.sale_price_list, self.compare_at_price_list) if name]

	def get_unpriced(self, item_codes: list[str]) -> set[str]:
		"""The items this market cannot sell: those with no price in either of its price lists."""
		if self.uses_store_prices or not item_codes:
			return set()
		return self.get_unavailable(item_codes)

	def get_unavailable(self, item_codes: list[str]) -> set[str]:
		"""Items neither list prices. A cart cannot sell them in any market, the primary one included."""
		sale, compare_at = self.get_base_rates(item_codes)
		return set(item_codes) - set(sale) - set(compare_at)

	def get_base_rates(self, item_codes: list[str]) -> tuple[dict[str, float], dict[str, float]]:
		"""(sale, compare-at) public rates by item code. Customer rows are negotiated contracts."""
		sale, compare_at = {}, {}
		for (item_code, price_list), row in get_base_price_rows_by_key(item_codes, self.price_lists).items():
			if price_list == self.sale_price_list:
				sale[item_code] = flt(row.price_list_rate)
			if price_list == self.compare_at_price_list:
				compare_at[item_code] = flt(row.price_list_rate)
		return sale, compare_at
