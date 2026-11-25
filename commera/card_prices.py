"""The price of a product card, one rule for the card, the grid filters, the sort and the facet.
A size sells at its sale rate, else its compare-at rate; the card shows its lowest-priced size."""

import frappe
from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import Coalesce, Max, Min
from frappe.utils import nowdate
from pypika.analytics import Min as WindowMin
from pypika.queries import QueryBuilder
from pypika.terms import Field, ValueWrapper

from commera.base_prices import can_use_direct_item_price, is_public_price, is_valid_on, public_rates_query


def get_card_price(size_rates: list[tuple[float | None, float | None]]) -> dict:
	"""Card prices from (sale, compare-at) rates per size. Mirrored in SQL by card_prices_query."""
	priced = [
		(sale if sale is not None else compare_at, sale, compare_at)
		for sale, compare_at in size_rates
		if sale is not None or compare_at is not None
	]
	if not priced:
		return {
			"effective_price": None,
			"sale_price": None,
			"default_price": None,
			**get_discount(None, None),
		}

	price = min(size_price for size_price, _sale, _compare_at in priced)
	cheapest = [(sale, compare_at) for size_price, sale, compare_at in priced if size_price == price]
	# Only a sale rate crosses out the compare-at rate, and only a higher one.
	crossed_out = [
		compare_at
		for sale, compare_at in cheapest
		if sale is not None and compare_at is not None and compare_at > price
	]
	default_price = max(crossed_out, default=None)
	return {
		"effective_price": price,
		"sale_price": price if any(sale is not None for sale, _compare_at in cheapest) else None,
		"default_price": default_price,
		**get_discount(price, default_price),
	}


def get_discount(price: float | None, default_price: float | None) -> dict:
	if not default_price:
		return {"discount_percent": 0.0, "has_discount": 0}
	# Rounded like the SQL decimal: 42.50 from 100 is 57.5% off, not 57.49999.
	return {"discount_percent": round((default_price - price) / default_price * 100, 6), "has_discount": 1}


def card_prices_query(
	sale_price_list: str | None, compare_at_price_list: str | None, products: list | QueryBuilder
):
	"""One row per product (`parent`) with get_card_price's effective, sale and default prices.
	Only `products` (names or a name subquery) are aggregated. A product with no priced size has no row."""
	sizes = size_prices_query(sale_price_list, compare_at_price_list, products).as_("sizes")
	sale, compare_at, size_price = (
		Field("sale", table=sizes),
		Field("compare_at", table=sizes),
		Field("size_price", table=sizes),
	)
	crossed_out = Case().when(sale.notnull() & (compare_at > size_price), compare_at)
	return (
		frappe.qb.from_(sizes)
		.where(size_price == Field("lowest_price", table=sizes))
		.groupby(Field("parent", table=sizes))
		.select(
			Field("parent", table=sizes),
			Min(size_price).as_("effective_price"),
			Max(Case().when(sale.notnull(), sale)).as_("sale_price"),
			Max(crossed_out).as_("default_price"),
		)
	)


def size_prices_query(
	sale_price_list: str | None, compare_at_price_list: str | None, products: list | QueryBuilder
):
	"""Each size of `products` with its rates, and the lowest size price of its product.
	Reads both price lists in a single pass instead of joining two derived tables."""
	size = DocType("Color Size Item").as_("priced_size")
	price_lists = list(dict.fromkeys(pl for pl in (sale_price_list, compare_at_price_list) if pl))

	if can_use_direct_item_price() and price_lists:
		price = DocType("Item Price").as_("public_price")
		sale_rate = (
			Min(Case().when(price.price_list == sale_price_list, price.price_list_rate))
			if sale_price_list
			else ValueWrapper(None)
		)
		compare_at_rate = (
			Min(Case().when(price.price_list == compare_at_price_list, price.price_list_rate))
			if compare_at_price_list
			else ValueWrapper(None)
		)
		size_price = Coalesce(sale_rate, compare_at_rate)
		return (
			frappe.qb.from_(size)
			.join(price)
			.on(
				(price.item_code == size.item_code)
				& price.price_list.isin(price_lists)
				& (price.selling == 1)
				& is_public_price(price)
				& is_valid_on(price, nowdate())
			)
			.where((size.parenttype == "Style Attribute Variant") & size.parent.isin(products))
			.groupby(size.parent, size.item_code)
			.select(
				size.parent,
				sale_rate.as_("sale"),
				compare_at_rate.as_("compare_at"),
				size_price.as_("size_price"),
				WindowMin(size_price).over(size.parent).as_("lowest_price"),
			)
		)

	listed = DocType("Color Size Item").as_("listed_size")
	item_codes = (
		frappe.qb.from_(listed)
		.select(listed.item_code)
		.where((listed.parenttype == "Style Attribute Variant") & listed.parent.isin(products))
	)
	rates = public_rates_query(price_lists or [""], item_codes).as_("size_rates")
	rate_pl = Field("price_list", table=rates)
	rate_val = Field("rate", table=rates)

	sale_rate = (
		Min(Case().when(rate_pl == sale_price_list, rate_val)) if sale_price_list else ValueWrapper(None)
	)
	compare_at_rate = (
		Min(Case().when(rate_pl == compare_at_price_list, rate_val))
		if compare_at_price_list
		else ValueWrapper(None)
	)
	size_price = Coalesce(sale_rate, compare_at_rate)
	return (
		frappe.qb.from_(size)
		.left_join(rates)
		.on(Field("item_code", table=rates) == size.item_code)
		.where((size.parenttype == "Style Attribute Variant") & size.parent.isin(products))
		.groupby(size.parent, size.item_code)
		.select(
			size.parent,
			sale_rate.as_("sale"),
			compare_at_rate.as_("compare_at"),
			size_price.as_("size_price"),
			# One read of the sizes: the product's lowest price is a window over the grouped sizes.
			WindowMin(size_price).over(size.parent).as_("lowest_price"),
		)
	)


def card_discount_percent(card):
	"""get_discount's percent over a card_prices_query table."""
	default_price = Field("default_price", table=card)
	return (
		Case()
		.when(
			default_price.notnull(),
			(default_price - Field("effective_price", table=card)) / default_price * 100,
		)
		.else_(0)
	)
