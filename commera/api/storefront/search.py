import frappe
from frappe.rate_limiter import rate_limit

from commera.sdk import catalog
from commera.sdk.types import ProductCard, Typeahead


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60)
def get_typeahead(query: str, limit: int = 6) -> Typeahead:
	return catalog.get_typeahead(query, limit=limit)


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60)
def get_recommendations(handle: str, limit: int = 8) -> list[ProductCard]:
	return catalog.get_recommendations(handle, limit=limit)
