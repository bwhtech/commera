"""The Item Price rows that set a public price. A customer row is a negotiated contract and a batch row
prices one batch: neither is what an anonymous shopper pays. Every storefront price read uses these."""

from frappe.query_builder.functions import IfNull

BASE_PRICE_FILTERS = {"customer": ("is", "not set"), "batch_no": ("is", "not set")}


def base_price_filters(filters: dict) -> dict:
	return {**filters, **BASE_PRICE_FILTERS}


def is_base_price(item_price):
	"""BASE_PRICE_FILTERS as a frappe.qb condition on an Item Price table."""
	return (IfNull(item_price.customer, "") == "") & (IfNull(item_price.batch_no, "") == "")
