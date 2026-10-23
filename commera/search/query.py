from frappe.search.sqlite_search import MAX_SEARCH_RESULTS

from commera.product_detail import size_sort_key
from commera.search.engine_cache import get_search_engine


def search_term(filters):
	return ((filters or {}).get("search") or "").strip()


def relevance_sort_available(filters):
	"""True when the active search engine can rank this term and so serve the grid."""
	return get_search_engine().can_rank(search_term(filters))


def use_qb_fallback(filters):
	"""True when the retained frappe.qb grid must serve this request instead of the search engine."""
	return not relevance_sort_available(filters)


def storefront_search(query, limit=20, facet_filters=None):
	"""Run the search engine and hydrate matched product names into storefront product cards."""
	engine = get_search_engine()
	result = engine.search(query, limit=limit, facet_filters=facet_filters)
	return {"products": build_product_cards(result["product_names"])}


def build_product_cards(product_names):
	"""Hydrate ranked variant names into product cards from the index, preserving rank order."""
	from commera.utils import attach_live_prices, shape_product_cards

	if not product_names:
		return []
	return shape_product_cards(attach_live_prices(get_search_engine().hydrate_cards(product_names)))


def listing_facets(selected_filters):
	"""Sidebar brand/color/size value-lists from the search engine, or None when frappe.qb owns the grid."""
	if use_qb_fallback(selected_filters):
		return None

	facets = get_search_engine().search(
		search_term(selected_filters), limit=MAX_SEARCH_RESULTS, facet_filters=selected_filters
	)["facets"]

	return {
		"brands": list(facets.get("brand") or {}),
		"colors": list(facets.get("color") or {}),
		"sizes": sorted(facets.get("size") or {}, key=size_sort_key),
	}
