import frappe

from commera.api.storefront import rate_limited_guest_api
from commera.sdk import catalog
from commera.sdk.types import ProductCard, Typeahead
from commera.storefront_cache import CATALOG_READ_DOMAINS, cached_guest_api


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_typeahead(query: str, limit: int = 6) -> Typeahead:
	return cached_guest_api(
		"search.get_typeahead",
		(query or "", int(limit)),
		CATALOG_READ_DOMAINS,
		lambda: catalog.get_typeahead(query, limit=limit),
		endpoint="commera.api.storefront.search.get_typeahead",
		ttl=60,
	)


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_recommendations(handle: str, limit: int = 8) -> list[ProductCard]:
	return cached_guest_api(
		"search.get_recommendations",
		(handle or "", int(limit)),
		CATALOG_READ_DOMAINS,
		lambda: catalog.get_recommendations(handle, limit=limit),
		endpoint="commera.api.storefront.search.get_recommendations",
		ttl=60,
	)
