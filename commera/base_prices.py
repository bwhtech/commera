"""Item Price rows as storefront prices. A public row has no customer, supplier or batch: a contract,
a buying price or one batch's price is not what an anonymous shopper pays. Every storefront read uses these."""

import frappe
from erpnext.stock.get_item_details import apply_item_price_order
from frappe.query_builder import Case, DocType, Order
from frappe.query_builder.functions import Coalesce, IfNull, NullIf
from frappe.utils import create_batch, nowdate
from pypika.analytics import RowNumber
from pypika.terms import ValueWrapper

from commera.utils import IN_CLAUSE_CHUNK_SIZE


def get_public_rates(item_codes: list[str], price_lists: list[str]) -> list[dict]:
	"""public_rates_query's rows for `item_codes`: item_code, price_list, rate and valid_upto."""
	price_lists = [name for name in price_lists if name]
	if not item_codes or not price_lists:
		return []
	rows = []
	for chunk in create_batch(list(item_codes), IN_CLAUSE_CHUNK_SIZE):
		rows.extend(public_rates_query(price_lists, chunk).run(as_dict=True))
	return rows


def public_rates_query(price_lists: list[str], item_codes):
	"""One row per item and list: the rate ERPNext's get_price_list_rate gives a new line today, in the
	item's sales UOM, from the item's rows, else its template's. The cart applies packing units."""
	# A union, not an OR join: each half reads Item Price by its item_code index.
	candidates = (
		get_candidate_rows(price_lists, item_codes, "name")
		* get_candidate_rows(price_lists, item_codes, "variant_of")
	).as_("price_candidates")
	ranked = (
		frappe.qb.from_(candidates)
		.select(
			candidates.item_code,
			candidates.price_list,
			candidates.rate,
			candidates.valid_upto,
			get_rank(candidates).as_("price_rank"),
		)
		.as_("ranked_prices")
	)
	return (
		frappe.qb.from_(ranked)
		.select(ranked.item_code, ranked.price_list, ranked.rate, ranked.valid_upto)
		.where(ranked.price_rank == 1)
	)


def get_candidate_rows(price_lists: list[str], item_codes, priced_by: str):
	"""The public rows valid today that price an item through its `priced_by` field: name or variant_of."""
	item = DocType("Item").as_("priced_item")
	price = DocType("Item Price").as_("public_price")
	sales_uom = get_sales_uom(item)
	query = (
		frappe.qb.from_(item)
		.join(price)
		.on(price.item_code == item[priced_by])
		.where(
			item.name.isin(item_codes)
			& price.price_list.isin(price_lists)
			& (price.selling == 1)
			& is_public_price(price)
			& is_valid_on(price, nowdate())
			& IfNull(price.uom, "").isin(["", sales_uom, item.stock_uom])
		)
		.select(
			item.name.as_("item_code"),
			price.price_list,
			price.valid_from,
			price.valid_upto,
			price.uom,
			price.name.as_("price_name"),
			ValueWrapper(int(priced_by != "name")).as_("template_rank"),
			Case().when(IfNull(price.uom, "").isin(["", sales_uom]), 0).else_(1).as_("uom_rank"),
		)
	)
	return add_sales_unit_rate(query, item, price)


def add_sales_unit_rate(query, item, price):
	"""The row's rate for one sales UOM, as get_price_list_rate_for converts it."""
	price_list = DocType("Price List").as_("public_price_list")
	own, template = (
		DocType("UOM Conversion Detail").as_("own_uom"),
		DocType("UOM Conversion Detail").as_("template_uom"),
	)
	sales_uom = get_sales_uom(item)
	rate = (
		Case()
		.when(
			(IfNull(price.uom, "") == sales_uom) | (price_list.price_not_uom_dependent == 1),
			price.price_list_rate,
		)
		.else_(price.price_list_rate * Coalesce(own.conversion_factor, template.conversion_factor, 1))
	)
	return (
		query.join(price_list)
		.on(price_list.name == price.price_list)
		.left_join(own)
		.on((own.parent == item.name) & (own.parenttype == "Item") & (own.uom == sales_uom))
		.left_join(template)
		.on(
			(template.parent == item.variant_of)
			& (template.parenttype == "Item")
			& (template.uom == sales_uom)
		)
		.select(rate.as_("rate"))
	)


def get_rank(candidates):
	"""The item's own rows before its template's, rows in the sales UOM before stock UOM rows, then
	erpnext.stock.get_item_details.apply_item_price_order."""
	return (
		RowNumber()
		.over(candidates.item_code, candidates.price_list)
		.orderby(candidates.template_rank)
		.orderby(candidates.uom_rank)
		.orderby(candidates.valid_from.isnull())
		.orderby(candidates.valid_from, order=Order.desc)
		.orderby(candidates.uom, order=Order.desc)
		.orderby(candidates.price_name, order=Order.desc)
	)


def get_sales_uom(item):
	return Coalesce(NullIf(item.sales_uom, ""), item.stock_uom)


def get_sales_units(item_codes: list[str]) -> dict[str, str]:
	"""The sales UOM of each item sold in a UOM other than its stock UOM: what one unit of its price buys."""
	if not item_codes:
		return {}
	rows = frappe.get_all(
		"Item", filters={"name": ["in", list(item_codes)]}, fields=["name", "sales_uom", "stock_uom"]
	)
	return {row.name: row.sales_uom for row in rows if row.sales_uom and row.sales_uom != row.stock_uom}


def get_public_price_rows(item_codes: list[str], price_lists: list[str], fields: list[str]) -> list[dict]:
	"""The public selling rows of `item_codes` on `price_lists` whatever their dates, for the price
	editors: the row in effect today first, then in ERPNext's order. Pass one chunk of codes."""
	if not item_codes or not price_lists:
		return []
	price = frappe.qb.DocType("Item Price")
	query = (
		frappe.qb.from_(price)
		.select(*(price[field] for field in fields))
		.where(
			price.item_code.isin(item_codes)
			& price.price_list.isin(price_lists)
			& (price.selling == 1)
			& is_public_price(price)
		)
		.orderby(Case().when(is_valid_on(price, nowdate()), 0).else_(1))
	)
	return apply_item_price_order(query, price).run(as_dict=True)


def is_public_price(item_price):
	return (
		(IfNull(item_price.customer, "") == "")
		& (IfNull(item_price.supplier, "") == "")
		& (IfNull(item_price.batch_no, "") == "")
	)


def is_valid_on(item_price, on_date):
	# The bounds erpnext.stock.get_item_details.get_item_price applies for a transaction date.
	return (IfNull(item_price.valid_from, "2000-01-01") <= on_date) & (
		IfNull(item_price.valid_upto, "2500-12-31") >= on_date
	)
