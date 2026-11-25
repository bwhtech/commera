"""Item Price rows as storefront prices. A public row has no customer, supplier or batch: a contract,
a buying price or one batch's price is not what an anonymous shopper pays. Every storefront read uses these."""

from contextlib import contextmanager

import frappe
from frappe.query_builder import Case, DocType, Order
from frappe.query_builder.functions import Coalesce, IfNull, NullIf, Round
from frappe.utils import create_batch, nowdate
from pypika.analytics import RowNumber
from pypika.terms import ValueWrapper

from commera.utils import IN_CLAUSE_CHUNK_SIZE

TEMPLATE_PRICES_CACHE_KEY = "commera:has_template_item_prices"
NON_STOCK_SALES_UOM_CACHE_KEY = "commera:has_non_stock_sales_uom"
MISMATCHED_PRICE_UOM_CACHE_KEY = "commera:has_mismatched_price_uom"
DUPLICATE_PRICES_CACHE_PREFIX = "commera:has_duplicate_active_prices:"


def has_template_item_prices() -> bool:
	"""Whether any selling Item Price row targets a template Item (has_variants=1).
	Cached in Redis and invalidated on Item Price writes so the common variant-priced shop skips the UNION."""
	cached = frappe.cache.get_value(TEMPLATE_PRICES_CACHE_KEY)
	if cached is not None:
		return bool(cached)
	item = DocType("Item")
	price = DocType("Item Price")
	exists = bool(
		frappe.qb.from_(price)
		.join(item)
		.on(item.name == price.item_code)
		.select(price.name)
		.where((price.selling == 1) & (item.has_variants == 1))
		.limit(1)
		.run()
	)
	frappe.cache.set_value(TEMPLATE_PRICES_CACHE_KEY, int(exists))
	return exists


def has_non_stock_sales_uom() -> bool:
	"""Whether any Item defines a sales_uom distinct from its stock_uom.
	When False, sales_uom == stock_uom everywhere and UOM conversion joins/subqueries are unnecessary."""
	cached = frappe.cache.get_value(NON_STOCK_SALES_UOM_CACHE_KEY)
	if cached is not None:
		return bool(cached)
	item = DocType("Item")
	exists = bool(
		frappe.qb.from_(item)
		.select(item.name)
		.where((IfNull(item.sales_uom, "") != "") & (item.sales_uom != item.stock_uom))
		.limit(1)
		.run()
	)
	frappe.cache.set_value(NON_STOCK_SALES_UOM_CACHE_KEY, int(exists))
	return exists


def has_mismatched_price_uom() -> bool:
	"""Whether any selling public Item Price specifies a UOM different from its Item's stock_uom."""
	cached = frappe.cache.get_value(MISMATCHED_PRICE_UOM_CACHE_KEY)
	if cached is not None:
		return bool(cached)
	item = DocType("Item")
	price = DocType("Item Price")
	exists = bool(
		frappe.qb.from_(price)
		.join(item)
		.on(item.name == price.item_code)
		.select(price.name)
		.where(
			(price.selling == 1)
			& is_public_price(price)
			& (IfNull(price.uom, "") != "")
			& (price.uom != item.stock_uom)
		)
		.limit(1)
		.run()
	)
	frappe.cache.set_value(MISMATCHED_PRICE_UOM_CACHE_KEY, int(exists))
	return exists


def has_duplicate_active_item_prices() -> bool:
	"""Whether any (item_code, price_list) has more than one active public selling Item Price today."""
	today = nowdate()
	cache_key = f"{DUPLICATE_PRICES_CACHE_PREFIX}{today}"
	cached = frappe.cache.get_value(cache_key)
	if cached is not None:
		return bool(cached)
	from frappe.query_builder.functions import Count

	price = DocType("Item Price")
	exists = bool(
		frappe.qb.from_(price)
		.select(price.item_code)
		.where((price.selling == 1) & is_public_price(price) & is_valid_on(price, today))
		.groupby(price.item_code, price.price_list)
		.having(Count("*") > 1)
		.limit(1)
		.run()
	)
	frappe.cache.set_value(cache_key, int(exists), expires_in_sec=24 * 60 * 60)
	return exists


def can_use_direct_item_price() -> bool:
	"""True when public selling prices are 1:1 per (item_code, price_list) on variant items in stock UOM.
	Allows direct Item Price reads without Item joins or ROW_NUMBER() windowing."""
	return (
		not has_template_item_prices()
		and not has_non_stock_sales_uom()
		and not has_mismatched_price_uom()
		and not has_duplicate_active_item_prices()
	)


def _delete_item_price_flags():
	frappe.cache.delete_value(TEMPLATE_PRICES_CACHE_KEY)
	frappe.cache.delete_value(MISMATCHED_PRICE_UOM_CACHE_KEY)
	frappe.cache.delete_keys(f"{DUPLICATE_PRICES_CACHE_PREFIX}*")


def clear_template_price_cache(doc=None, method=None, *args, **kwargs):
	_delete_item_price_flags()
	clear_request_rates_cache()
	if hasattr(frappe.db, "after_commit"):
		frappe.db.after_commit.add(_delete_item_price_flags)


def clear_sales_uom_cache(doc=None, method=None, *args, **kwargs):
	frappe.cache.delete_value(NON_STOCK_SALES_UOM_CACHE_KEY)
	frappe.cache.delete_value(MISMATCHED_PRICE_UOM_CACHE_KEY)
	clear_request_rates_cache()
	if hasattr(frappe.db, "after_commit"):
		frappe.db.after_commit.add(
			lambda: (
				frappe.cache.delete_value(NON_STOCK_SALES_UOM_CACHE_KEY),
				frappe.cache.delete_value(MISMATCHED_PRICE_UOM_CACHE_KEY),
			)
		)


def clear_request_rates_cache():
	if cache := getattr(frappe.local, "commera_public_rates_cache", None):
		cache.clear()


def clear_base_prices_cache():
	_delete_item_price_flags()
	frappe.cache.delete_value(NON_STOCK_SALES_UOM_CACHE_KEY)
	clear_request_rates_cache()


@contextmanager
def memoize_public_rates():
	"""Memoize get_public_rates within a single read-only storefront call (e.g. list_products)."""
	existing = getattr(frappe.local, "commera_public_rates_cache", None)
	if existing is not None:
		yield
		return
	frappe.local.commera_public_rates_cache = {}
	try:
		yield
	finally:
		frappe.local.commera_public_rates_cache = None


def get_public_rates(item_codes: list[str], price_lists: list[str]) -> list[dict]:
	"""public_rates_query's rows for `item_codes`: item_code, price_list, rate and valid_upto."""
	price_lists = list(dict.fromkeys(name for name in price_lists if name))
	if not item_codes or not price_lists:
		return []
	unique_codes = list(dict.fromkeys(item_codes))
	cache = getattr(frappe.local, "commera_public_rates_cache", None)
	cache_key = (tuple(sorted(unique_codes)), tuple(price_lists), nowdate()) if cache is not None else None
	if cache is not None and cache_key in cache:
		return cache[cache_key]

	rows = []
	if can_use_direct_item_price() and len(unique_codes) > IN_CLAUSE_CHUNK_SIZE:
		# Large catalog-wide reads (e.g. inventory report): one indexed price_list scan beats multi-chunk IN (...).
		wanted = set(unique_codes)
		price = DocType("Item Price").as_("public_price")
		all_rows = (
			frappe.qb.from_(price)
			.select(
				price.item_code,
				price.price_list,
				price.price_list_rate.as_("rate"),
				price.valid_upto,
				price.name.as_("price_name"),
				price.price_list_rate,
				ValueWrapper(0).as_("template_rank"),
			)
			.where(
				price.price_list.isin(price_lists)
				& (price.selling == 1)
				& is_public_price(price)
				& is_valid_on(price, nowdate())
			)
			.run(as_dict=True)
		)
		rows = [row for row in all_rows if row.item_code in wanted]
	else:
		for chunk in create_batch(unique_codes, IN_CLAUSE_CHUNK_SIZE):
			rows.extend(public_rates_query(price_lists, chunk).run(as_dict=True))
	if cache is not None:
		cache[cache_key] = rows
	return rows


def public_rates_query(price_lists: list[str], item_codes):
	"""One row per item and list: the rate ERPNext's get_price_list_rate gives a new line today, in the
	item's sales UOM, from the item's rows, else its template's. price_name is the row; the cart applies packing units."""
	if can_use_direct_item_price():
		price = DocType("Item Price").as_("public_price")
		return (
			frappe.qb.from_(price)
			.select(
				price.item_code,
				price.price_list,
				price.price_list_rate.as_("rate"),
				price.valid_upto,
				price.name.as_("price_name"),
				price.price_list_rate,
				ValueWrapper(0).as_("template_rank"),
			)
			.where(
				price.item_code.isin(item_codes)
				& price.price_list.isin(price_lists)
				& (price.selling == 1)
				& is_public_price(price)
				& is_valid_on(price, nowdate())
			)
		)

	if has_template_item_prices():
		# A union, not an OR join: each half reads Item Price by its item_code index.
		candidates = (
			get_candidate_rows(price_lists, item_codes, "name")
			* get_candidate_rows(price_lists, item_codes, "variant_of")
		).as_("price_candidates")
	else:
		candidates = get_candidate_rows(price_lists, item_codes, "name").as_("price_candidates")
	ranked = (
		frappe.qb.from_(candidates)
		.select(
			candidates.item_code,
			candidates.price_list,
			candidates.rate,
			candidates.valid_upto,
			candidates.price_name,
			candidates.price_list_rate,
			candidates.template_rank,
			get_rank(candidates).as_("price_rank"),
		)
		.as_("ranked_prices")
	)
	return (
		frappe.qb.from_(ranked)
		.select(
			ranked.item_code,
			ranked.price_list,
			ranked.rate,
			ranked.valid_upto,
			ranked.price_name,
			ranked.price_list_rate,
			ranked.template_rank,
		)
		.where(ranked.price_rank == 1)
	)


def get_candidate_rows(price_lists: list[str], item_codes, priced_by: str):
	"""The public rows valid today that price an item through its `priced_by` field: name or variant_of."""
	item = DocType("Item").as_("priced_item")
	price = DocType("Item Price").as_("public_price")
	use_uom_conversion = has_non_stock_sales_uom()
	sales_uom = get_sales_uom(item) if use_uom_conversion else item.stock_uom
	uom_filter = (
		IfNull(price.uom, "").isin(["", sales_uom, item.stock_uom])
		if use_uom_conversion
		else IfNull(price.uom, "").isin(["", item.stock_uom])
	)
	uom_rank = (
		Case().when(IfNull(price.uom, "").isin(["", sales_uom]), 0).else_(1)
		if use_uom_conversion
		else ValueWrapper(0)
	)

	where_cond = (
		item.name.isin(item_codes)
		& price.price_list.isin(price_lists)
		& (price.selling == 1)
		& is_public_price(price)
		& is_valid_on(price, nowdate())
		& uom_filter
	)
	if priced_by == "variant_of":
		where_cond = where_cond & (IfNull(item.variant_of, "") != "")

	query = (
		frappe.qb.from_(item)
		.join(price)
		.on(price.item_code == item[priced_by])
		.where(where_cond)
		.select(
			item.name.as_("item_code"),
			price.price_list,
			price.valid_from,
			price.valid_upto,
			price.uom,
			price.name.as_("price_name"),
			price.price_list_rate,
			ValueWrapper(int(priced_by != "name")).as_("template_rank"),
			uom_rank.as_("uom_rank"),
		)
	)
	if not use_uom_conversion:
		return query.select(price.price_list_rate.as_("rate"))
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
			(IfNull(item.sales_uom, "") == "")
			| (item.sales_uom == item.stock_uom)
			| (IfNull(price.uom, "") == sales_uom)
			| (price_list.price_not_uom_dependent == 1),
			price.price_list_rate,
		)
		.else_(
			price.price_list_rate
			* Coalesce(
				own.conversion_factor, template.conversion_factor, get_global_conversion_factor(item), 1
			)
		)
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


def get_global_conversion_factor(item):
	"""The UOM Conversion Factor from the sales UOM to the stock UOM, as erpnext.stock.doctype.item.item
	.get_uom_conv_factor reads it for an item without its own conversion row."""
	sales_uom = get_sales_uom(item)
	exact, inverse = get_factor_value(sales_uom, item.stock_uom), get_factor_value(item.stock_uom, sales_uom)
	precision = frappe.get_precision("UOM Conversion Factor", "value")
	return Coalesce(exact, Round(ValueWrapper(1) / inverse, precision))


def get_factor_value(from_uom, to_uom):
	factor = DocType("UOM Conversion Factor")
	return (
		frappe.qb.from_(factor)
		.select(factor.value)
		.where((factor.from_uom == from_uom) & (factor.to_uom == to_uom) & (factor.value > 0))
		.limit(1)
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
	if not item_codes or not has_non_stock_sales_uom():
		return {}
	rows = frappe.get_all(
		"Item", filters={"name": ["in", list(item_codes)]}, fields=["name", "sales_uom", "stock_uom"]
	)
	return {row.name: row.sales_uom for row in rows if row.sales_uom and row.sales_uom != row.stock_uom}


def get_todays_price_rows(item_codes: list[str], price_lists: list[str]) -> list[dict]:
	"""The item's own row each storefront read uses today, for the price editors. An item priced only by
	expired, future or template rows has none: as in ERPNext's insert_item_price, an edit adds a row from today."""
	return [row for row in get_public_rates(item_codes, price_lists) if not row.template_rank]


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
