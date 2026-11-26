from frappe.utils.data import cint

from commera.api.storefront import rate_limited_guest_api
from commera.sdk import catalog
from commera.sdk.types import ProductCard, Typeahead
from commera.storefront_cache import CATALOG_READ_DOMAINS, cached_guest_api


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_typeahead(query: str, limit: int = 6) -> Typeahead:
	# Free-text queries are uncached to avoid unbounded Redis key writes.
	return catalog.get_typeahead(query, limit=limit)


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_recommendations(handle: str, limit: int = 8) -> list[ProductCard]:
	norm_limit = cint(limit) or 8
	if not handle or norm_limit < 1 or norm_limit > 12:
		return catalog.get_recommendations(handle, limit=limit)
	return cached_guest_api(
		"search.get_recommendations",
		(handle, norm_limit),
		CATALOG_READ_DOMAINS,
		lambda: catalog.get_recommendations(handle, limit=limit),
		endpoint="commera.api.storefront.search.get_recommendations",
		ttl=60,
		should_cache=bool,
	)
