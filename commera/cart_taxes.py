"""The taxes of a cart: the shopper's Tax Rule, else the market's own template, else, outside the primary
market, the company default. Inclusive or exclusive follows each template row's `included_in_print_rate`."""

import frappe
from erpnext.accounts.doctype.tax_rule.tax_rule import get_tax_template
from erpnext.accounts.party import get_address_tax_category, set_taxes
from frappe import _
from frappe.model import child_table_fields, default_fields
from frappe.utils.data import nowdate

from commera.localization.markets import Market

TEMPLATE_DOCTYPE = "Sales Taxes and Charges Template"


def apply_market_taxes(quotation, market: Market | None, switched: bool):
	"""Resolve unpaid cart taxes for the cart's market and its current address."""
	if quotation.docstatus or (
		quotation.name
		and frappe.db.exists(
			"Gateway Payment Request",
			{"ref_doctype": "Quotation", "ref_docname": quotation.name, "status": "Paid"},
		)
	):
		return
	own_template = get_own_template(market, quotation.company)
	template = (
		get_tax_rule_template(quotation, market) or own_template or get_default_template(quotation, market)
	)
	is_market_template = bool(own_template) and template == own_template
	if not switched and not is_market_template and has_address_taxes(quotation):
		return
	quotation.commera_market_tax_template = own_template if is_market_template else None
	# ERPNext's party lookup would name a Tax Rule template this cart left out, without its rows.
	if "taxes_and_charges" not in quotation.dont_update_if_missing:
		quotation.dont_update_if_missing.append("taxes_and_charges")
	if not is_template_applied(quotation, template):
		set_tax_template(quotation, template)


def clear_address_taxes(quotation):
	"""The cart's address changed, so a template chosen for the old address no longer holds.
	Rows added without a template were not chosen for an address, and stay."""
	if quotation.taxes_and_charges:
		set_tax_template(quotation, None)


def has_address_taxes(quotation) -> bool:
	"""Taxes that regional code, such as India's GST, set for the cart's address. They stand until the
	address or the market changes. Commera's own charges, and a template the market put on the cart, do not count."""
	# Imported here: commera.api.shipping imports the cart, which imports this module.
	from commera.api.shipping import is_cart_charge

	if not any(not is_cart_charge(row, quotation) for row in quotation.get("taxes") or []):
		return False
	template = quotation.taxes_and_charges
	if not template:
		return True
	return (
		template != quotation.get("commera_market_tax_template")
		and is_usable(template, quotation.company)
		and is_template_applied(quotation, template)
	)


def is_template_applied(quotation, template: str | None) -> bool:
	"""The cart names `template` and has its rows. ERPNext's validate can name a template without adding them."""
	# Imported here: commera.api.shipping imports the cart, which imports this module.
	from commera.api.shipping import is_cart_charge, matches_tax_row

	if (quotation.taxes_and_charges or None) != template:
		return False
	rows = [row for row in quotation.get("taxes") or [] if not is_cart_charge(row, quotation)]
	expected = get_template_rows(template)
	return len(rows) == len(expected) and all(map(matches_tax_row, rows, expected))


def get_own_template(market: Market | None, company: str) -> str | None:
	"""The market's template. One that cannot tax this company's quotation is refused, not replaced:
	a silent fallback would charge the shopper a different rate."""
	if not market or not market.tax_template:
		return None
	if not is_usable(market.tax_template, company):
		frappe.throw(
			_(
				"Taxes for {0} cannot be calculated: its tax template {1} is disabled or belongs to another company."
			).format(market.title, market.tax_template),
			title=_("Taxes Not Available"),
		)
	return market.tax_template


def is_usable(template: str, company: str) -> bool:
	values = frappe.get_cached_value(TEMPLATE_DOCTYPE, template, ["company", "disabled"])
	return bool(values) and values[0] == company and not values[1]


def get_default_template(quotation, market: Market | None) -> str | None:
	"""A secondary market falls back to the company's default template. The primary market keeps
	ERPNext's behavior, which has no such fallback."""
	if is_primary(market):
		return None
	return frappe.db.get_value(
		TEMPLATE_DOCTYPE, {"company": quotation.company, "is_default": 1, "disabled": 0}
	)


def get_tax_rule_template(quotation, market: Market | None = None) -> str | None:
	"""The Tax Rule ERPNext's shopping cart finds for the shopper. Before the cart has an address, the rule
	is matched against the market's country, so a rule for the store's country does not tax other markets."""
	if quotation.quotation_to != "Customer" or not quotation.party_name:
		return None
	customer = frappe.get_cached_value(
		"Customer", quotation.party_name, ["customer_group", "tax_category"], as_dict=True
	)
	if not customer:
		return None
	billing, shipping = quotation.customer_address, quotation.shipping_address_name
	tax_category = get_address_tax_category(customer.tax_category, billing, shipping)
	# A Quotation has no posting_date; with None, ERPNext skips every dated rule.
	date = quotation.transaction_date or nowdate()
	if billing or shipping:
		return set_taxes(
			quotation.party_name,
			"Customer",
			date,
			quotation.company,
			customer_group=customer.customer_group,
			tax_category=tax_category,
			billing_address=billing,
			shipping_address=shipping,
			use_for_shopping_cart=1,
		)
	country = get_market_country(market)
	args = {
		"customer": quotation.party_name,
		"company": quotation.company,
		"customer_group": customer.customer_group,
		"tax_category": tax_category,
		"billing_country": country,
		"shipping_country": country,
		"tax_type": "Sales",
		"use_for_shopping_cart": 1,
	}
	return get_tax_template(date, args)


def get_market_country(market: Market | None) -> str | None:
	"""The Country a cart without an address ships to: the store's in the primary market, else the
	shopper's country when the market has it, else the market's first country."""
	from commera.localization.resolver import get_localization
	from commera.utils import get_store_company

	if is_primary(market):
		company = get_store_company()
		return frappe.get_cached_value("Company", company, "country") if company else None
	code = get_localization().country
	code = code if code in market.countries else next(iter(market.countries), None)
	return frappe.db.get_value("Country", {"code": code})


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


def is_primary(market: Market | None) -> bool:
	return not market or market.is_primary
