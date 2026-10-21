import frappe
from frappe.utils import flt
from frappe.utils.caching import redis_cache

from commera import seo
from commera.search import query as search_query
from commera.search.facets import get_product_filters
from commera.shop_data import find_menu_root, get_storefront_menu
from commera.swatches import get_swatch_map
from commera.utils import (
	PAGE_SIZE_OPTIONS,
	get_current_page,
	get_nested_links,
	get_page_size,
	get_product_list,
	get_total_product_count,
)

no_cache = 1


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
	category_root = get_category_root(selected_filters["category"])
	# An unknown ?category= is shopper-typed text that must never be echoed; the other filters still apply.
	if not category_root:
		selected_filters["category"] = ""
	filters, price_range = get_product_filters(selected_filters)
	context.page_length = get_page_size()
	context.page_size_options = PAGE_SIZE_OPTIONS
	context.show_relevance_sort = search_query.relevance_sort_available(selected_filters)
	context.sort_by = get_sort_by("default" if context.show_relevance_sort else "new_arrival")
	context.products = get_product_list(
		filters=selected_filters,
		page=page,
		page_length=context.page_length,
		sort_by=context.sort_by,
	)
	context.current_page = page
	context.total_count = get_total_product_count(filters=selected_filters)
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

	context.seo = seo.build_collection_seo(
		context.category,
		context.breadcrumbs,
		total_count=context.total_count,
		category_doc=category_root,
	)
	context.json_ld = [
		seo.build_collection_json_ld(context.category, context.breadcrumbs, context.total_count),
		seo.build_breadcrumb_json_ld(context.breadcrumbs),
	]
