import frappe
from frappe.rate_limiter import rate_limit

from commera.search.typeahead import DEFAULT_LIMIT, Typeahead, get_typeahead


# Catalogue search is public and rate limited; it returns only published products.
@frappe.whitelist(allow_guest=True)  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=120, seconds=60)
def typeahead(q: str, limit: int = DEFAULT_LIMIT) -> Typeahead:
	"""Search as you type: product cards, matching menu entries and a "Did you mean" query."""
	return get_typeahead(q, limit)
