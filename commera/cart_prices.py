"""The cart in its market: the market's price lists and currency, never converted. A line sells at its
sale rate, else its compare-at rate, as on product pages. A line with neither is unavailable."""

import frappe
from frappe import _
from frappe.utils.data import flt

from commera.localization.market_prices import MarketPrices
from commera.localization.markets import PRIMARY_MARKET, Market, StorefrontMarkets

MARKET_FIELD = "commera_market"


def apply_market(quotation, prices: MarketPrices):
	"""Point the quotation at the market before ERPNext prices its lines, and record which market.
	A switch clears the old exchange rates, so ERPNext reads the new ones."""
	is_priced = is_priced_in(quotation, prices)
	quotation.set(MARKET_FIELD, prices.handle)
	if is_priced:
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


def is_priced_in(doc, prices: MarketPrices) -> bool:
	"""Priced in the market of `prices`, as its sale list and currency stand now."""
	priced = (get_market_handle(doc), doc.selling_price_list, doc.currency)
	return priced == (prices.handle, prices.sale_price_list, prices.currency)


def get_market_handle(doc) -> str:
	# Empty on staff-made documents and on carts priced before the field: the store's prices.
	return doc.get(MARKET_FIELD) or PRIMARY_MARKET


def price_regular_lines(quotation, prices: MarketPrices):
	"""Before ERPNext prices new lines from the sale list: a line only the compare-at list prices takes
	that rate. ERPNext keeps a price_list_rate that is set, and derives the rate from it."""
	new_lines = [item for item in quotation.items if not flt(item.price_list_rate)]
	sale, compare_at = prices.get_base_rates([item.item_code for item in new_lines])
	for item in new_lines:
		if item.item_code not in sale and item.item_code in compare_at:
			item.price_list_rate = compare_at[item.item_code]
			item.rate = 0


def get_document_market(doc) -> Market | None:
	"""The market `doc` was priced in, hidden markets included. None once it is deleted."""
	return StorefrontMarkets.load(include_hidden=True).find(get_market_handle(doc))


def get_document_prices(doc) -> MarketPrices:
	"""The prices of `doc`'s market. The store's when it has none, or its market is deleted."""
	return MarketPrices.of(get_document_market(doc))


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
