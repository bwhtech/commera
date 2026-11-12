"""The Item Price rows that set a public price today. A customer row is a negotiated contract, a supplier
row is a buying price and a batch row prices one batch: none is what an anonymous shopper pays. A row
outside its valid_from/valid_upto is no price, as in ERPNext. Every storefront price read uses these."""

import frappe
from frappe.query_builder.functions import IfNull
from frappe.utils import nowdate


def is_base_price(item_price, on_date=None):
	"""A frappe.qb condition on an Item Price table: a public row valid on `on_date` (default today)."""
	return is_public_price(item_price) & is_valid_on(item_price, on_date or nowdate())


def is_public_price(item_price):
	return (
		(IfNull(item_price.customer, "") == "")
		& (IfNull(item_price.supplier, "") == "")
		& (IfNull(item_price.batch_no, "") == "")
	)


def is_valid_on(item_price, on_date):
	# The bounds erpnext.stock.get_item_details.get_item_price applies for a transaction date.
	return (IfNull(item_price.valid_from, "2000-01-01") <= on_date) & (
		IfNull(item_price.valid_upto, "2500-12-31") >= on_date
	)


def get_base_price_rows(item_codes: list[str], price_lists: list[str], fields: list[str]) -> list[dict]:
	"""The base selling rows of `item_codes` on `price_lists`, oldest first. Pass one chunk of codes."""
	if not item_codes or not price_lists:
		return []
	price = frappe.qb.DocType("Item Price")
	return (
		frappe.qb.from_(price)
		.select(*(price[field] for field in fields))
		.where(
			price.item_code.isin(item_codes)
			& price.price_list.isin(price_lists)
			& (price.selling == 1)
			& is_base_price(price)
		)
		.orderby(price.creation)
		.run(as_dict=True)
	)
