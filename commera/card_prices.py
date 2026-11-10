"""The price of a product card, one rule for the card, the grid filters, the sort and the facet.
A size sells at its sale rate, else its compare-at rate; the card shows its lowest-priced size."""

import frappe
from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import Coalesce, Max, Min
from pypika.terms import Field

from commera.base_prices import is_base_price


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
	return {"discount_percent": (default_price - price) / default_price * 100, "has_discount": 1}


def card_prices_query(sale_price_list: str | None, compare_at_price_list: str | None):
	"""One row per product (`parent`) with get_card_price's effective, sale and default prices.
	A product with no priced size has no row."""
	sizes = size_prices_query(sale_price_list, compare_at_price_list).as_("sizes")
	lowest_sizes = size_prices_query(sale_price_list, compare_at_price_list).as_("lowest_sizes")
	lowest = (
		frappe.qb.from_(lowest_sizes)
		.groupby(Field("parent", table=lowest_sizes))
		.select(
			Field("parent", table=lowest_sizes),
			Min(Field("size_price", table=lowest_sizes)).as_("price"),
		)
	).as_("lowest")

	sale, compare_at, size_price = (
		Field("sale", table=sizes),
		Field("compare_at", table=sizes),
		Field("size_price", table=sizes),
	)
	crossed_out = Case().when(sale.notnull() & (compare_at > size_price), compare_at)
	return (
		frappe.qb.from_(sizes)
		.join(lowest)
		.on(
			(Field("parent", table=sizes) == Field("parent", table=lowest))
			& (size_price == Field("price", table=lowest))
		)
		.groupby(Field("parent", table=sizes))
		.select(
			Field("parent", table=sizes),
			Min(size_price).as_("effective_price"),
			Max(Case().when(sale.notnull(), sale)).as_("sale_price"),
			Max(crossed_out).as_("default_price"),
		)
	)


def size_prices_query(sale_price_list: str | None, compare_at_price_list: str | None):
	color_size_item = DocType("Color Size Item")
	sale = DocType("Item Price").as_("size_sale")
	compare_at = DocType("Item Price").as_("size_compare_at")
	sale_rate, compare_at_rate = Min(sale.price_list_rate), Min(compare_at.price_list_rate)
	return (
		frappe.qb.from_(color_size_item)
		.left_join(sale)
		.on(
			(sale.item_code == color_size_item.item_code)
			& (sale.price_list == sale_price_list)
			& is_base_price(sale)
		)
		.left_join(compare_at)
		.on(
			(compare_at.item_code == color_size_item.item_code)
			& (compare_at.price_list == compare_at_price_list)
			& is_base_price(compare_at)
		)
		.where(color_size_item.parenttype == "Style Attribute Variant")
		.groupby(color_size_item.parent, color_size_item.item_code)
		.select(
			color_size_item.parent,
			sale_rate.as_("sale"),
			compare_at_rate.as_("compare_at"),
			Coalesce(sale_rate, compare_at_rate).as_("size_price"),
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
