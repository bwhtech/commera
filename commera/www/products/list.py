import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Min
from frappe.utils import flt
from frappe.utils.caching import redis_cache

from commera import seo
from commera.product_detail import size_sort_key
from commera.search import query as search_query
from commera.shop_data import find_menu_root, get_category_facets, get_storefront_menu
from commera.swatches import get_swatch_map
from commera.utils import (
	PAGE_SIZE_OPTIONS,
	get_current_page,
	get_nested_links,
	get_page_size,
	get_product_base_query,
	get_product_list,
	get_total_product_count,
)

no_cache = 1


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


def get_product_filters(selected_filters):
	"""Fetches available filters like brand, price range, and sizes."""
	category = selected_filters.get("category", "")
	item_price = DocType("Item Price")
	sale_price_list = frappe.get_cached_value("Commera Settings", "Commera Settings", "sale_price_list")
	price_range = (
		frappe.qb.from_(item_price)
		.select(
			Min(item_price.price_list_rate).as_("min_price"),
			frappe.query_builder.functions.Max(item_price.price_list_rate).as_("max_price"),
		)
		.where(item_price.price_list == sale_price_list)
	).run(as_dict=True)

	filters = get_category_facets(category)

	# When SQLite serves the grid, faceting from the same result set stops dead filter options.
	facets = search_query.listing_facets(selected_filters)
	if facets:
		filters.update(facets)
	else:
		filters["brands"] = get_filter_brands(selected_filters)
		filters["sizes"] = get_filter_sizes(selected_filters)
		filters["colors"] = get_filter_colors(selected_filters)

	return filters, price_range[0] if price_range else {"min_price": 0, "max_price": 0}


def get_selected_filters():
	"""Extracts filters from URL query parameters."""
	query_params = frappe.form_dict

	filters = {
		"subcategory": query_params.get("subcategory", "").split(",")
		if query_params.get("subcategory")
		else [],
		"colors": query_params.get("colors", "").split(",") if query_params.get("colors") else [],
		"sizes": query_params.get("sizes", "").split(",") if query_params.get("sizes") else [],
		"brands": query_params.get("brands", "").split(",") if query_params.get("brands") else [],
		"search": query_params.get("search", ""),
		"category": query_params.get("category", ""),
		"has_discount": query_params.get("has_discount", "0") == "1",
	}
	min_price = query_params.get("min")
	max_price = query_params.get("max")

	# flt, not int: the price slider posts decimals (?min=74.5), which int() rejects with a 500.
	if min_price:
		filters["min_price"] = flt(min_price)
	if max_price:
		filters["max_price"] = flt(max_price)
	return filters


def get_sort_by(default_sort):
	return frappe.form_dict.get("sort_by") or default_sort


def get_category_root(category):
	return find_menu_root(get_storefront_menu(), category) if category else None


def get_context(context):
	page = get_current_page()
	selected_filters = get_selected_filters()
	requested_category = selected_filters["category"]
	category_root = get_category_root(requested_category)
	# An unknown ?category= is shopper-typed text: it must never be echoed or stand in for the whole catalog.
	unknown_category = bool(requested_category and not category_root)
	if unknown_category:
		selected_filters["category"] = ""
	filters, price_range = get_product_filters(selected_filters)
	context.page_length = get_page_size()
	context.page_size_options = PAGE_SIZE_OPTIONS
	context.show_relevance_sort = search_query.relevance_sort_available(selected_filters)
	context.sort_by = get_sort_by("default" if context.show_relevance_sort else "new_arrival")
	context.products = (
		[]
		if unknown_category
		else get_product_list(
			filters=selected_filters,
			page=page,
			page_length=context.page_length,
			sort_by=context.sort_by,
		)
	)
	context.current_page = page
	context.total_count = 0 if unknown_category else get_total_product_count(filters=selected_filters)
	context.filters = filters
	context.selected_filters = selected_filters
	context.swatches = get_swatch_map()
	context.price_range = price_range
	context.breadcrumbs = [
		{
			"label": "Products",
			"href": "#",
		}
	]
	context.category = category_root["label"] if category_root else ""

	category_doc = seo.get_category_seo_overrides(selected_filters["category"])
	context.seo = seo.build_collection_seo(
		context.category,
		context.breadcrumbs,
		total_count=context.total_count,
		category_doc=category_doc,
	)
	context.json_ld = [
		seo.build_collection_json_ld(context.category, context.breadcrumbs, context.total_count),
		seo.build_breadcrumb_json_ld(context.breadcrumbs),
	]
