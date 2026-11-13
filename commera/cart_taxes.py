"""The taxes of a cart: the shopper's Tax Rule, else the market's own template, else, outside the primary
market, the company default. Inclusive or exclusive follows each template row's `included_in_print_rate`."""

import frappe
from erpnext.accounts.doctype.tax_rule.tax_rule import get_tax_rule_party_details, get_tax_template
from erpnext.accounts.party import get_address_tax_category
from erpnext.setup.doctype.customer_group.customer_group import get_parent_customer_groups
from frappe import _
from frappe.model import child_table_fields, default_fields
from frappe.query_builder import Criterion
from frappe.query_builder.functions import IfNull
from frappe.utils.data import nowdate
from frappe.utils.nestedset import get_root_of

from commera.localization.markets import Market

TEMPLATE_DOCTYPE = "Sales Taxes and Charges Template"
SPECIFIC_RULE_FIELDS = ("customer", "customer_group", "tax_category", "billing_country", "shipping_country")


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
	if has_unmanaged_rows(quotation) or (
		not switched and not is_market_template and has_address_taxes(quotation)
	):
		return
	quotation.commera_market_tax_template = own_template if is_market_template else None
	# ERPNext's party lookup would name a Tax Rule template this cart left out, without its rows.
	if "taxes_and_charges" not in quotation.dont_update_if_missing:
		quotation.dont_update_if_missing.append("taxes_and_charges")
	if not is_template_applied(quotation, template):
		set_tax_template(quotation, template, managed=True)


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

	if not any(
		not row.get("commera_cart_charge") and not is_cart_charge(row, quotation)
		for row in quotation.get("taxes") or []
	):
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
	return len(rows) == len(expected) and all(
		matches_tax_row(row, tax) for row, tax in zip(rows, expected, strict=True)
	)


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
	"""Use ERPNext matching and ranking, excluding generic rules when the market has a template."""
	customer_name = quotation.party_name if quotation.quotation_to == "Customer" else None
	customer = (
		frappe.get_cached_value("Customer", customer_name, ["customer_group", "tax_category"], as_dict=True)
		if customer_name
		else None
	)
	billing, shipping = quotation.customer_address, quotation.shipping_address_name
	args = {
		"customer": customer_name,
		"company": quotation.company,
		"tax_category": get_address_tax_category(
			customer.tax_category if customer else "", billing, shipping
		),
		"tax_type": "Sales",
		"use_for_shopping_cart": 1,
	}
	if customer:
		args.update(customer_group=customer.customer_group)
	if billing or shipping:
		args.update(
			get_tax_rule_party_details(
				customer_name, "Customer", {"billing_address": billing, "shipping_address": shipping}
			)
		)
	else:
		country = get_market_country(market)
		args.update(billing_country=country, shipping_country=country)
	date = quotation.transaction_date or nowdate()
	if not market or not market.tax_template:
		return get_tax_template(date, args)
	return get_specific_rule_template(date, args)


def get_specific_rule_template(date: str, args: dict) -> str | None:
	"""ERPNext's `get_tax_template` over rules with a `SPECIFIC_RULE_FIELDS` condition. ERPNext has no
	candidate filter, so this repeats its matching, ranking and disabled check in one query."""
	rule = frappe.qb.DocType("Tax Rule")
	query = (
		frappe.qb.from_(rule)
		.select(rule.star)
		.where(rule.from_date.isnull() | (rule.from_date <= date))
		.where(rule.to_date.isnull() | (rule.to_date >= date))
		.where(Criterion.any([IfNull(rule[field], "") != "" for field in SPECIFIC_RULE_FIELDS]))
	)
	for key, value in args.items():
		query = query.where(get_rule_condition(rule, key, value))
	rules = query.run(as_dict=True)
	if not rules:
		return None
	# More matched conditions win, then the higher priority. A disabled template stops the search.
	best = max(rules, key=lambda row: (sum(bool(row.get(key)) for key in args), row.priority or 0))
	if frappe.db.get_value(TEMPLATE_DOCTYPE, best.sales_tax_template, "disabled"):
		return None
	return best.sales_tax_template


def get_rule_condition(rule, key: str, value):
	"""ERPNext `get_tax_template`'s condition on one argument."""
	if key == "use_for_shopping_cart":
		return rule.use_for_shopping_cart == value
	if key == "tax_category":
		return IfNull(rule.tax_category, "") == (value or "")
	if key == "customer_group":
		parents = get_parent_customer_groups(value or get_root_of("Customer Group"))
		return IfNull(rule.customer_group, "").isin(["", *(group.name for group in parents)])
	return IfNull(rule[key], "").isin(["", value or ""])


def get_market_country(market: Market | None) -> str | None:
	"""Prefer the shopper's known country, including unclaimed countries in the primary market."""
	from commera.localization.resolver import get_localization
	from commera.utils import get_store_company

	code = get_localization().country
	if not code and market:
		code = next(iter(market.countries), None)
	if code:
		return frappe.db.get_value("Country", {"code": code})
	company = get_store_company()
	return frappe.get_cached_value("Company", company, "country") if company else None


def has_unmanaged_rows(quotation) -> bool:
	"""Commera may replace only its own template rows, never a caller's manual taxes."""
	from commera.api.shipping import is_cart_charge

	return any(
		not is_managed_tax_row(row, quotation) and not is_cart_charge(row, quotation)
		for row in quotation.get("taxes") or []
	)


def is_managed_tax_row(row, quotation) -> bool:
	from commera.api.shipping import is_applied_template_row

	if row.get("commera_cart_charge") == "tax_template":
		return True
	if any(tax.get("commera_cart_charge") == "tax_template" for tax in quotation.taxes):
		return False
	# Old carts have no provenance. Recognize their applied template until the next rebuild.
	return bool(quotation.taxes_and_charges) and is_applied_template_row(row, quotation)


def set_tax_template(quotation, template: str | None, *, managed: bool = False):
	"""The template's rows first, so their row references hold, then Commera's own charges."""
	# Imported here: commera.api.shipping imports the cart, which imports this module.
	from commera.api.shipping import keep_shipping_rule_last

	charges = [row for row in quotation.get("taxes") or [] if not is_managed_tax_row(row, quotation)]
	quotation.taxes_and_charges = template
	quotation.set(
		"taxes",
		[
			{**row, "commera_cart_charge": "tax_template" if managed else ""}
			for row in get_template_rows(template)
		],
	)
	for row in charges:
		quotation.append("taxes", row)
	keep_shipping_rule_last(quotation)
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
