import frappe
from frappe.utils import create_batch
from frappe.utils.data import cstr, flt

from commera.api.admin.catalog import get_default_rates, get_selling_rates
from commera.api.admin.orders import get_reporting_currency
from commera.app_events import get_ecommerce_warehouse, get_listed_items
from commera.sdk.types import CatalogItem
from commera.utils import IN_CLAUSE_CHUNK_SIZE, get_available_stocks

__all__ = ["get_items"]


def get_items(item_codes: list[str]) -> dict[str, CatalogItem]:
	"""`price` is what a shopper pays, `list_price` the struck-through figure; both None until the store's
	price lists are set. A code that is not an Item is left out."""
	frappe.has_permission("Item", ptype="read", throw=True)
	items = {}
	for item_code_chunk in create_batch(
		list({cstr(item_code) for item_code in item_codes}), IN_CLAUSE_CHUNK_SIZE
	):
		items.update(read_items(item_code_chunk))
	return items


def read_items(item_codes: list[str]) -> dict[str, CatalogItem]:
	rows = frappe.get_all(
		"Item", filters={"name": ["in", item_codes]}, fields=["name", "item_name", "variant_of"]
	)
	found_codes = [row.name for row in rows]
	if not found_codes:
		return {}

	listed_items = get_listed_items(found_codes)
	prices, list_prices = get_store_prices(found_codes)
	warehouse = get_ecommerce_warehouse()
	# get_available_stocks reads a missing warehouse as one literally named "website_warehouse".
	stocks = get_available_stocks(found_codes, warehouse) if warehouse else {}
	currency = get_reporting_currency()

	return {
		row.name: {
			"item_code": row.name,
			"title": row.item_name,
			"product": row.variant_of or row.name,
			"is_listed": row.name in listed_items,
			"price": prices.get(row.name),
			"list_price": list_prices.get(row.name),
			"currency": currency,
			"available_qty": flt(stocks.get(row.name, {}).get("stock_qty")),
			"unlimited": bool(stocks.get(row.name, {}).get("unlimited")),
		}
		for row in rows
	}


def get_store_prices(item_codes: list[str]) -> tuple[dict, dict]:
	price_lists = frappe.get_cached_value(
		"Commera Settings", "Commera Settings", ["default_price_list", "sale_price_list"]
	)
	if not all(price_lists):
		return {}, {}
	return get_selling_rates(item_codes), get_default_rates(item_codes)
