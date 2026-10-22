import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count, Max, Min

from commera.product_detail import size_sort_key
from commera.search import query as search_query
from commera.shop_data import get_category_facets
from commera.utils import get_product_base_query


def get_filter_brands(filters=None):
	filter_copy = filters.copy() if filters else {}
	filter_copy.pop("brands", None)

	query = get_product_base_query(filter_copy)
	item = DocType("Item")

	query = query.select(item.brand).distinct().orderby(item.brand)
	# Raw values: they round-trip into a case-sensitive SQLite IN on the index.
	return [brand for brand in query.run(pluck=True) if brand]


def get_filter_colors(filters=None):
	filter_copy = filters.copy() if filters else {}
	filter_copy.pop("colors", None)

	query = get_product_base_query(filter_copy)
	variant = DocType("Style Attribute Variant")

	query = query.select(variant.attribute_value).distinct().orderby(variant.attribute_value)
	return [color for color in query.run(pluck=True) if color]


def get_filter_sizes(filters=None):
	filter_copy = filters.copy() if filters else {}
	filter_copy.pop("sizes", None)

	query = get_product_base_query(filter_copy)
	color_size_item = DocType("Color Size Item")

	query = query.select(color_size_item.size).distinct()
	return sorted(query.run(pluck=True), key=size_sort_key)


# The facet's filter key, and the doctype and field its values come from.
FACET_FIELDS = {
	"brands": ("Item", "brand"),
	"colors": ("Style Attribute Variant", "attribute_value"),
	"sizes": ("Color Size Item", "size"),
}


def get_facet_counts_qb(filters: dict, key: str) -> dict[str, int]:
	"""Published products per value of one facet, narrowed by every filter but the facet's own."""
	filter_copy = filters.copy()
	filter_copy.pop(key, None)
	doctype, fieldname = FACET_FIELDS[key]
	column = DocType(doctype)[fieldname]
	variant = DocType("Style Attribute Variant")

	rows = (
		get_product_base_query(filter_copy)
		.select(column.as_("value"), Count(variant.name).distinct().as_("count"))
		.where(column.notnull() & (column != ""))
		.groupby(column)
		.orderby(column)
	).run(as_dict=True)
	counts = {row.value: row.count for row in rows}
	if key == "sizes":
		return {size: counts[size] for size in sorted(counts, key=size_sort_key)}
	return counts


def get_listing_facet_counts(selected_filters: dict) -> dict[str, dict[str, int]]:
	"""Brand, colour and size product counts from the engine that serves the grid."""
	counts = search_query.listing_facet_counts(selected_filters)
	if counts is not None:
		return counts
	return {key: get_facet_counts_qb(selected_filters, key) for key in FACET_FIELDS}


def get_price_range() -> dict:
	item_price = DocType("Item Price")
	sale_price_list = frappe.get_cached_value("Commera Settings", "Commera Settings", "sale_price_list")
	price_range = (
		frappe.qb.from_(item_price)
		.select(
			Min(item_price.price_list_rate).as_("min_price"),
			Max(item_price.price_list_rate).as_("max_price"),
		)
		.where(item_price.price_list == sale_price_list)
	).run(as_dict=True)
	return price_range[0] if price_range else {"min_price": 0, "max_price": 0}


def get_product_filters(selected_filters):
	"""Fetches available filters like brand, price range, and sizes."""
	category = selected_filters.get("category", "")
	filters = get_category_facets(category)

	# When SQLite serves the grid, faceting from the same result set stops dead filter options.
	facets = search_query.listing_facets(selected_filters)
	if facets:
		filters.update(facets)
	else:
		filters["brands"] = get_filter_brands(selected_filters)
		filters["sizes"] = get_filter_sizes(selected_filters)
		filters["colors"] = get_filter_colors(selected_filters)

	return filters, get_price_range()
