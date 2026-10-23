import frappe

from commera.product_detail import size_sort_key
from commera.search.engine_cache import get_search_engine
from commera.search.http_client import SearchServerError


def search_term(filters):
	return ((filters or {}).get("search") or "").strip()


def relevance_sort_available(filters):
	"""True when the active search engine can rank this term and so serve the grid."""
	return get_search_engine().can_rank(search_term(filters))


def use_qb_fallback(filters):
	"""True when the retained frappe.qb grid must serve this request instead of the search engine."""
	return not relevance_sort_available(filters)


def read_or_fall_back(read, fall_back):
	"""Serve `read()` from the engine, or `fall_back()` from frappe.qb when the search server fails.
	The cached readiness lets the first request of an outage reach the server, so it must not raise."""
	try:
		return read()
	except SearchServerError as error:
		frappe.logger("commera.search").warning(str(error))
		get_search_engine().mark_unavailable()
		return fall_back()


def build_product_cards(product_names):
	"""Hydrate ranked variant names into product cards from the index, preserving rank order."""
	from commera.utils import attach_live_prices, shape_product_cards

	if not product_names:
		return []
	return shape_product_cards(attach_live_prices(get_search_engine().hydrate_cards(product_names)))


def listing_facets(selected_filters):
	"""Sidebar brand/color/size value-lists from the search engine, or None when frappe.qb owns the grid."""
	counts = listing_facet_counts(selected_filters)
	return {key: list(values) for key, values in counts.items()} if counts is not None else None


def listing_facet_counts(selected_filters):
	"""Brand/color/size product counts from the search engine, or None when frappe.qb owns the grid."""
	if use_qb_fallback(selected_filters):
		return None

	facets = read_or_fall_back(lambda: get_search_engine().facet_counts(selected_filters), lambda: None)
	if facets is None:
		return None

	sizes = facets.get("size") or {}
	return {
		"brands": facets.get("brand") or {},
		"colors": facets.get("color") or {},
		"sizes": {size: sizes[size] for size in sorted(sizes, key=size_sort_key)},
	}
