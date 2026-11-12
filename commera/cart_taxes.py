"""The taxes of a cart in its market: the market's own template, else the template ERPNext picks.
Inclusive or exclusive follows each template row's `included_in_print_rate`."""

import frappe
from erpnext.accounts.party import get_address_tax_category, set_taxes
from frappe.model import child_table_fields, default_fields

from commera.localization.markets import Market

TEMPLATE_DOCTYPE = "Sales Taxes and Charges Template"


def apply_market_taxes(quotation, market: Market | None, switched: bool):
	"""Resolve unpaid cart taxes independently of price changes."""
	if quotation.docstatus or (
		quotation.name
		and frappe.db.exists(
			"Gateway Payment Request",
			{"ref_doctype": "Quotation", "ref_docname": quotation.name, "status": "Paid"},
		)
	):
		return
	if own_template := get_own_template(market, quotation.company):
		set_tax_template(quotation, own_template)
		quotation.commera_market_tax_template = own_template
		return
	managed = quotation.get("commera_market_tax_template")
	quotation.commera_market_tax_template = None
	if (
		not switched
		and (not managed or quotation.taxes_and_charges != managed)
		and has_usable_taxes(quotation)
	):
		return
	if is_primary(market) and not has_taxes(quotation):
		return
	set_tax_template(quotation, get_default_template(quotation, market))


def has_usable_taxes(quotation) -> bool:
	template = quotation.taxes_and_charges
	if not template:
		return bool(quotation.get("taxes"))
	company, disabled = frappe.get_cached_value(TEMPLATE_DOCTYPE, template, ["company", "disabled"]) or (
		None,
		1,
	)
	return company == quotation.company and not disabled


def get_own_template(market: Market | None, company: str) -> str | None:
	"""The market's template, if it can still tax this company's quotation."""
	if not market or not market.tax_template:
		return None
	template_company, disabled = frappe.get_cached_value(
		TEMPLATE_DOCTYPE, market.tax_template, ["company", "disabled"]
	) or (None, 1)
	return market.tax_template if template_company == company and not disabled else None


def get_default_template(quotation, market: Market | None) -> str | None:
	"""ERPNext's choice: the shopper's Tax Rule. A secondary market falls back to the company's
	default template; the primary market keeps today's behavior, which has no such fallback."""
	if template := get_tax_rule_template(quotation):
		return template
	if is_primary(market):
		return None
	return frappe.db.get_value(
		TEMPLATE_DOCTYPE, {"company": quotation.company, "is_default": 1, "disabled": 0}
	)


def get_tax_rule_template(quotation) -> str | None:
	"""The Tax Rule ERPNext's party details find for the shopper, with the same arguments."""
	if quotation.quotation_to != "Customer" or not quotation.party_name:
		return None
	customer = frappe.get_cached_value(
		"Customer", quotation.party_name, ["customer_group", "tax_category"], as_dict=True
	)
	if not customer:
		return None
	billing, shipping = quotation.customer_address, quotation.shipping_address_name
	return set_taxes(
		quotation.party_name,
		"Customer",
		quotation.get("posting_date"),
		quotation.company,
		customer_group=customer.customer_group,
		tax_category=get_address_tax_category(customer.tax_category, billing, shipping),
		billing_address=billing,
		shipping_address=shipping,
	)


def set_tax_template(quotation, template: str | None):
	"""The template's rows first, so their row references hold, then Commera's own charges."""
	# Imported here: commera.api.shipping imports the cart, which imports this module.
	from commera.api.shipping import is_cart_charge

	charges = [row for row in quotation.get("taxes") or [] if is_cart_charge(row, quotation)]
	quotation.taxes_and_charges = template
	quotation.set("taxes", get_template_rows(template))
	for row in charges:
		quotation.append("taxes", row)
	for index, row in enumerate(quotation.taxes, start=1):
		row.idx = index


def get_template_rows(template: str | None) -> list[dict]:
	"""Read without the shopper's permission, like the rest of cart pricing."""
	if not template:
		return []
	skipped = {*default_fields, *child_table_fields}
	rows = frappe.get_cached_doc(TEMPLATE_DOCTYPE, template).taxes
	return [{key: value for key, value in row.as_dict().items() if key not in skipped} for row in rows]


def has_taxes(quotation) -> bool:
	return bool(quotation.taxes_and_charges or quotation.get("taxes"))


def is_primary(market: Market | None) -> bool:
	return not market or market.is_primary
