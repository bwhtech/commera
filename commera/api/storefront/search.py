import frappe

from commera.api.storefront import rate_limited_guest_api
from commera.sdk import catalog
from commera.sdk.types import ProductCard, Typeahead


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_typeahead(query: str, limit: int = 6) -> Typeahead:
	return catalog.get_typeahead(query, limit=limit)


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_recommendations(handle: str, limit: int = 8) -> list[ProductCard]:
	return catalog.get_recommendations(handle, limit=limit)
