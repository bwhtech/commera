"""The cart in its market: the market's price lists and currency, never converted. A line sells at its
sale rate, else its compare-at rate, as on product pages. A line with neither is unavailable."""

import frappe
from frappe import _
from frappe.query_builder.functions import IfNull
from frappe.utils.data import add_days, date_diff, flt, nowdate

from commera.base_prices import is_valid_on
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
	move_to_today(quotation)
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


def move_to_today(quotation):
	"""Every sync prices the lines afresh, so at today's Item Prices, as the storefront shows them."""
	today = nowdate()
	if quotation.valid_till and quotation.transaction_date:
		quotation.valid_till = add_days(today, date_diff(quotation.valid_till, quotation.transaction_date))
	quotation.transaction_date = today


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
	"""Before ERPNext prices new lines from the sale list: a line the sale list has no row for takes its
	price from the compare-at list. ERPNext keeps a price_list_rate that is set, and derives the rate."""
	for item in quotation.items:
		if flt(item.price_list_rate):
			continue
		price_list, rate = get_line_price(quotation, item, prices)
		if price_list and price_list != prices.sale_price_list:
			item.price_list_rate = rate
			item.rate = 0


def get_line_price(quotation, item, prices: MarketPrices) -> tuple[str | None, float | None]:
	"""The first market list with a row for the line, and ERPNext's rate on it: the item's, else its
	template's, as get_price_list_rate. A list whose rows fit no quantity of the line refuses it."""
	from erpnext.stock.get_item_details import get_price_list_rate_for

	template = frappe.get_cached_value("Item", item.item_code, "variant_of")
	item_codes = [code for code in (item.item_code, template) if code]
	for price_list in prices.price_lists:
		context = get_price_context(quotation, item, price_list)
		if not (packing_units := get_packing_units(context, item_codes)):
			continue
		rates = (get_price_list_rate_for(context, code) for code in item_codes)
		if (rate := next((rate for rate in rates if rate is not None), None)) is None:
			frappe.throw(
				_("{0} sells in multiples of {1} in this market.").format(
					describe_items({item.item_code}), min((unit for unit in packing_units if unit), default=1)
				),
				title=_("Not Available"),
			)
		return price_list, rate
	return None, None


def get_price_context(quotation, item, price_list: str) -> dict:
	"""What get_price_list_rate_for reads for the line: the customer's own row before the public one,
	the line's UOM, its quantity and the quotation's date."""
	from erpnext.stock.get_item_details import get_conversion_factor

	stock_uom, sales_uom = frappe.get_cached_value("Item", item.item_code, ["stock_uom", "sales_uom"])
	# The UOM erpnext.stock.get_item_details gives a new selling line.
	uom = item.uom or sales_uom or stock_uom
	return {
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
	}


def get_packing_units(context: dict, item_codes: list[str]) -> list[float]:
	"""The packing units of the rows get_item_price can find for the line: none when the list has no row."""
	price = frappe.qb.DocType("Item Price")
	return (
		frappe.qb.from_(price)
		.select(IfNull(price.packing_unit, 0))
		.where(
			price.item_code.isin(item_codes)
			& (price.price_list == context["price_list"])
			& IfNull(price.customer, "").isin(["", context["customer"] or ""])
			& (IfNull(price.supplier, "") == "")
			& (IfNull(price.batch_no, "") == "")
			& IfNull(price.uom, "").isin(["", context["uom"], context["stock_uom"]])
			& is_valid_on(price, context["transaction_date"])
		)
		.run(pluck=True)
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
