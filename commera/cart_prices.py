"""The cart in its market: the market's price lists and currency, never converted. A line sells at its
sale rate, else its compare-at rate, as on product pages. A line with neither is unavailable."""

import frappe
from frappe import _
from frappe.utils.data import flt

from commera.localization.market_prices import MarketPrices
from commera.localization.markets import StorefrontMarkets


def apply_market(quotation, prices: MarketPrices):
	"""Point the quotation at the market's sale list and currency before ERPNext prices its lines.
	A switch clears the old exchange rates, so ERPNext reads the new ones."""
	if is_priced_in(quotation, prices):
		return
	quotation.update(
		{
			"selling_price_list": prices.sale_price_list,
			"currency": prices.currency,
			"price_list_currency": None,
			"plc_conversion_rate": None,
			"conversion_rate": None,
		}
	)


def is_priced_in(quotation, prices: MarketPrices) -> bool:
	return (quotation.selling_price_list, quotation.currency) == (prices.sale_price_list, prices.currency)


def price_regular_lines(quotation, prices: MarketPrices):
	"""Before ERPNext prices new lines from the sale list: a line only the compare-at list prices takes
	that rate. ERPNext keeps a price_list_rate that is set, and derives the rate from it."""
	new_lines = [item for item in quotation.items if not flt(item.price_list_rate)]
	sale, compare_at = prices.get_base_rates([item.item_code for item in new_lines])
	for item in new_lines:
		if item.item_code not in sale and item.item_code in compare_at:
			item.price_list_rate = compare_at[item.item_code]
			item.rate = 0


def get_priced_market(doc) -> MarketPrices | None:
	"""The prices of the market whose sale list and currency `doc` uses, hidden markets included."""
	for market in StorefrontMarkets.load(include_hidden=True).all:
		if is_priced_in(doc, prices := MarketPrices.of(market)):
			return prices
	return None


def validate_available(prices: MarketPrices, item_codes: list[str], message: str | None = None):
	"""`message` takes the products and sizes the market has no price for."""
	if unavailable := prices.get_unavailable(sorted(set(item_codes))):
		frappe.throw(
			(message or _("{0} is not available in this market.")).format(describe_items(unavailable)),
			title=_("Not Available"),
		)


def describe_items(item_codes: set[str]) -> str:
	# Imported here: the catalog behind the line titles imports the cart, which imports this module.
	from commera.sdk.lines import LineProducts

	products = LineProducts(list(item_codes))
	return ", ".join(sorted(products.get_label(item_code) for item_code in item_codes))
