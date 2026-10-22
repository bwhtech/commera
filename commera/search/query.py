import re

from frappe.search.sqlite_search import MAX_SEARCH_RESULTS

from commera.product_detail import size_sort_key
from commera.search.engine import MIN_QUERY_LENGTH
from commera.search.engine_cache import get_search_engine

ARABIC_PATTERN = re.compile("[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


def is_arabic_query(text):
	"""True if the text carries any Arabic-script character."""
	return bool(ARABIC_PATTERN.search(text or ""))


def search_term(filters):
	return ((filters or {}).get("search") or "").strip()


def relevance_sort_available(filters):
	"""True when a rankable term (≥ floor, non-Arabic) plus a live index lets SQLite serve the grid.

	The FTS tokenizer has no Arabic stemming, so an Arabic term is routed back to frappe.qb.
	"""
	term = search_term(filters)
	if len(term) < MIN_QUERY_LENGTH or is_arabic_query(term):
		return False
	return get_search_engine().index_exists()


def use_qb_fallback(filters):
	"""True when the retained frappe.qb grid must serve this request instead of SQLite."""
	return not relevance_sort_available(filters)


def storefront_search(query, limit=20, facet_filters=None):
	"""Run the FTS engine and hydrate matched product names into storefront product cards."""
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
	"""Sidebar brand/color/size value-lists from the FTS engine, or None when frappe.qb owns the grid."""
	counts = listing_facet_counts(selected_filters)
	return {key: list(values) for key, values in counts.items()} if counts is not None else None


def listing_facet_counts(selected_filters):
	"""Brand/color/size product counts from the FTS engine, or None when frappe.qb owns the grid."""
	if use_qb_fallback(selected_filters):
		return None

	facets = get_search_engine().search(
		search_term(selected_filters), limit=MAX_SEARCH_RESULTS, facet_filters=selected_filters
	)["facets"]

	sizes = facets.get("size") or {}
	return {
		"brands": facets.get("brand") or {},
		"colors": facets.get("color") or {},
		"sizes": {size: sizes[size] for size in sorted(sizes, key=size_sort_key)},
	}
