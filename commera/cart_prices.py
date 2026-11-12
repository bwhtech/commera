"""The cart in its market: the market's price lists and currency, never converted. A line sells at its
sale rate, else its compare-at rate, as on product pages. A line with neither is unavailable."""

import frappe
from frappe import _
from frappe.utils.data import flt, nowdate

from commera.cart_taxes import apply_market_taxes
from commera.localization.market_prices import MarketPrices
from commera.localization.markets import PRIMARY_MARKET, Market, StorefrontMarkets
from commera.localization.resolver import get_localization

MARKET_FIELD = "commera_market"


def apply_market(quotation, prices: MarketPrices):
	"""Point the quotation at the market's prices and taxes before ERPNext prices its lines, and
	record the market and language. A switch clears the old exchange rates, so ERPNext reads the new ones."""
	is_priced = is_priced_in(quotation, prices)
	switched = get_market_handle(quotation) != prices.handle
	quotation.set(MARKET_FIELD, prices.handle)
	# ERPNext's print language: the order prints in the language the shopper bought in.
	quotation.language = get_localization().language.code
	apply_market_taxes(quotation, get_document_market(quotation), switched=switched)
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
	priced = (doc.selling_price_list, doc.currency) == (prices.sale_price_list, prices.currency)
	# Before migrate creates the field it never saves; matching on it would rebuild on every load.
	if not frappe.get_meta(doc.doctype).has_field(MARKET_FIELD):
		return priced
	return priced and get_market_handle(doc) == prices.handle


def get_market_handle(doc) -> str:
	# Empty on staff-made documents and on carts priced before the field: the store's prices.
	return doc.get(MARKET_FIELD) or PRIMARY_MARKET


def price_regular_lines(quotation, prices: MarketPrices):
	"""Before ERPNext prices new lines from the sale list: a line the sale list has no price for takes
	ERPNext's price from the compare-at list. ERPNext keeps a price_list_rate that is set, and derives
	the rate from it."""
	if not prices.compare_at_price_list:
		return
	for item in quotation.items:
		if flt(item.price_list_rate) or get_list_rate(quotation, item, prices.sale_price_list) is not None:
			continue
		if (rate := get_list_rate(quotation, item, prices.compare_at_price_list)) is not None:
			item.price_list_rate = rate
			item.rate = 0


def get_list_rate(quotation, item, price_list: str) -> float | None:
	"""ERPNext's rate for the line on `price_list`, in the line's UOM: the customer's own row before the
	public one, valid on the quotation's date. None when the list has no such row."""
	from erpnext.stock.get_item_details import get_conversion_factor, get_price_list_rate_for

	stock_uom, sales_uom = frappe.get_cached_value("Item", item.item_code, ["stock_uom", "sales_uom"])
	# The UOM erpnext.stock.get_item_details gives a new selling line.
	uom = item.uom or sales_uom or stock_uom
	return get_price_list_rate_for(
		{
			"price_list": price_list,
			"customer": quotation.party_name if quotation.quotation_to == "Customer" else None,
			"uom": uom,
			"stock_uom": stock_uom,
			"conversion_factor": item.conversion_factor
			or get_conversion_factor(item.item_code, uom)["conversion_factor"],
			"price_list_uom_dependant": frappe.get_cached_value(
				"Price List", price_list, "price_not_uom_dependent"
			),
			"transaction_date": quotation.transaction_date or nowdate(),
			"qty": item.qty,
		},
		item.item_code,
	)


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
