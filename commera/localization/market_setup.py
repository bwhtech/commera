"""Validate only new market setup violations, so existing bad data can still be repaired."""

from contextlib import contextmanager
from functools import wraps

import frappe
from frappe import _
from frappe.query_builder import DocType

from commera.core import get_default_customer_group
from commera.shipping.pricing import has_delivery_options
from commera.utils import get_store_company, get_store_currency

MARKET_DOCTYPE = "Commera Market"
TAX_TEMPLATE_DOCTYPE = "Sales Taxes and Charges Template"
MULTI_CURRENCY_FIELD = "allow_multi_currency_invoices_against_single_party_account"


@contextmanager
def market_field(fieldname):
	"""The dashboard shows the error under this field of the market editor."""
	try:
		yield
	except frappe.ValidationError as error:
		if not getattr(error, "field", None):
			error.field = fieldname
		raise


def validates_field(fieldname):
	def decorate(validate):
		@wraps(validate)
		def wrapped(*args, **kwargs):
			with market_field(fieldname):
				return validate(*args, **kwargs)

		return wrapped

	return decorate


class MarketStoreFit:
	"""The checks that read the store setup too. `settings` is Commera Settings, maybe not saved yet."""

	def __init__(self, market, settings=None):
		settings = settings or frappe.get_cached_doc("Commera Settings")
		self.market = market
		self.company = settings.company or get_store_company()
		self.shipping_rule = settings.shipping_rule

	def validate(self):
		self.validate_tax_template()
		self.validate_invoice_currency()
		self.validate_delivery_countries()

	@validates_field("tax_template")
	def validate_tax_template(self):
		"""Carts are quoted by the store company, and ERPNext refuses another company's template."""
		if not (template := self.market.get("tax_template")):
			return
		company, disabled = frappe.db.get_value(TAX_TEMPLATE_DOCTYPE, template, ["company", "disabled"]) or (
			None,
			0,
		)

		if company != self.company:
			frappe.throw(
				_(
					"Market {0} uses tax template {1} of {2}. Choose a template of the store company {3}."
				).format(*self.bold(self.market.market_name, template, company, self.company)),
				title=_("Invalid Tax Template"),
			)
		# A cart would drop the template silently and charge the company default taxes.
		if disabled:
			frappe.throw(
				_("Tax template {0} of market {1} is disabled. Choose another template.").format(
					*self.bold(template, self.market.market_name)
				),
				title=_("Invalid Tax Template"),
			)

	@validates_field("sale_price_list")
	def validate_invoice_currency(self):
		"""Reject only currencies with no configured company or default customer-group route."""
		company_currency = get_store_currency(self.company)
		if self.market.currency in (None, company_currency) or frappe.db.get_single_value(
			"Accounts Settings", MULTI_CURRENCY_FIELD
		):
			return
		currencies = get_receivable_currencies(self.company)
		if self.market.currency in currencies:
			return

		frappe.throw(
			_(
				"Market {0} sells in {1}, but {2} keeps its accounts in {3}. ERPNext can invoice orders in {1}"
				" with {4} in Accounts Settings or a receivable account in {1}. Configure either route, or use {3}."
			).format(
				*self.bold(self.market.market_name, self.market.currency, self.company, company_currency),
				frappe.bold(_(frappe.get_meta("Accounts Settings").get_label(MULTI_CURRENCY_FIELD).strip())),
			),
			title=_("Currency Cannot Be Invoiced"),
		)

	@validates_field("countries")
	def validate_delivery_countries(self, countries=None, missing=None):
		"""Only refuse a missing country when no alternate delivery configuration exists."""
		if missing is None:
			countries = countries if countries is not None else [row.country for row in self.market.countries]
			missing = get_countries_without_delivery(self.shipping_rule, countries)
		if missing:
			frappe.throw(
				_(
					"The store Shipping Rule {0} does not deliver to {1}, a country of market {2}. Add {1} to"
					" the Shipping Rule, or remove it from the market."
				).format(*self.bold(self.shipping_rule, missing[0], self.market.market_name)),
				title=_("No Delivery"),
			)

	def bold(self, *values):
		return [frappe.bold(value) for value in values]


def validate_markets_for_store(settings):
	"""Check only invariants changed by these store settings."""
	if settings.is_new() or frappe.flags.in_patch or frappe.flags.in_migrate:
		return
	before = settings.get_doc_before_save() or frappe.get_doc("Commera Settings")
	if settings.has_value_changed("company"):
		validate_store_company(settings, before)
	if settings.has_value_changed("shipping_rule"):
		validate_store_delivery(settings, before)


def validate_store_company(settings, before):
	markets = frappe.get_all(
		MARKET_DOCTYPE, filters={"enabled": 1}, fields=["market_name", "currency", "tax_template"]
	)
	templates = {
		row.name: row.company for row in frappe.get_all(TAX_TEMPLATE_DOCTYPE, fields=["name", "company"])
	}
	old_company = before.company or get_store_company()
	old_currencies = get_receivable_currencies(old_company) | {get_store_currency(old_company)}
	currencies = get_receivable_currencies(settings.company) | {get_store_currency(settings.company)}
	multi_currency = frappe.db.get_single_value("Accounts Settings", MULTI_CURRENCY_FIELD)
	for market in markets:
		fit = MarketStoreFit(market, settings)
		# A company change can repair a mismatch without repairing a disabled template too.
		template_company = templates.get(market.tax_template)
		if template_company == old_company and template_company != settings.company:
			fit.validate_tax_template()
		if not multi_currency and market.currency in old_currencies and market.currency not in currencies:
			fit.validate_invoice_currency()


def validate_store_delivery(settings, before):
	rows = get_all_market_countries()
	countries = [country for country, _ in rows]
	old_missing = set(get_countries_without_delivery(before.shipping_rule, countries))
	new_missing = set(get_countries_without_delivery(settings.shipping_rule, countries)) - old_missing
	for country, market in rows:
		if country in new_missing:
			MarketStoreFit(frappe._dict(market_name=market), settings).validate_delivery_countries(
				missing=[country]
			)


def get_receivable_currencies(company):
	accounts = frappe.get_all(
		"Party Account",
		filters={"parenttype": "Customer Group", "parent": get_default_customer_group(), "company": company},
		pluck="account",
	)
	accounts.append(frappe.get_cached_value("Company", company, "default_receivable_account"))
	return set(
		frappe.get_all(
			"Account", filters={"name": ("in", [a for a in accounts if a])}, pluck="account_currency"
		)
	)


def validate_price_list(doc, method=None):
	"""Refuse a Price List change that a market's checkout would fail on."""
	# Before the schema sync no market has a price list.
	if doc.is_new() or not frappe.db.has_column(MARKET_DOCTYPE, "sale_price_list"):
		return
	markets = frappe.get_all(
		MARKET_DOCTYPE,
		filters={"enabled": 1},
		or_filters={"sale_price_list": doc.name, "compare_at_price_list": doc.name},
		fields=["name", "market_name", "sale_price_list"],
	)
	if not markets:
		return
	if doc.has_value_changed("currency"):
		throw_price_list_in_use(
			_("Price List {0} sets the prices of market {1}, so its currency cannot change."), doc, markets[0]
		)
	if any(doc.has_value_changed(field) and not doc.get(field) for field in ("enabled", "selling")):
		throw_price_list_in_use(
			_(
				"Price List {0} sets the prices of market {1}, so it must stay enabled and selling."
				" Choose another price list for the market first."
			),
			doc,
			markets[0],
		)
	if doc.has_value_changed("countries"):
		validate_price_list_countries(
			doc, [market for market in markets if market.sale_price_list == doc.name]
		)


def validate_price_list_countries(doc, markets: list[dict]):
	"""ERPNext refuses a sale to an address outside the sale list's countries. No countries: all."""
	if not (countries := {row.country for row in doc.countries}):
		return
	before = doc.get_doc_before_save()
	old_countries = {row.country for row in before.countries} if before else set()
	rows = frappe.get_all(
		"Commera Market Country",
		filters={"parent": ("in", [m.name for m in markets]), "parenttype": MARKET_DOCTYPE},
		fields=["parent", "country"],
	)
	for market in markets:
		if missing := [
			row.country
			for row in rows
			if row.parent == market.name
			and row.country not in countries
			and (not old_countries or row.country in old_countries)
		]:
			frappe.throw(
				_(
					"Price List {0} sets the prices of market {1}, which includes {2}. Keep {2} in its"
					" countries, or remove it from the market first."
				).format(frappe.bold(doc.name), frappe.bold(market.market_name), frappe.bold(missing[0])),
				title=_("Price List In Use"),
			)


def throw_price_list_in_use(message: str, doc, market: dict):
	frappe.throw(
		message.format(frappe.bold(doc.name), frappe.bold(market.market_name)), title=_("Price List In Use")
	)


def validate_tax_template(doc, method=None):
	"""Refuse to disable a market's template, or move it to another company."""
	if doc.is_new() or not frappe.db.has_column(MARKET_DOCTYPE, "tax_template"):
		return
	if not (
		(doc.has_value_changed("disabled") and doc.disabled)
		or (
			doc.has_value_changed("company")
			and doc.company != get_store_company()
			and doc.get_doc_before_save().company == get_store_company()
		)
	):
		return
	if market := frappe.db.get_value(MARKET_DOCTYPE, {"tax_template": doc.name, "enabled": 1}, "market_name"):
		frappe.throw(
			_(
				"Tax template {0} sets the taxes of market {1}, so it must stay enabled in the store company."
				" Choose another template for the market first."
			).format(frappe.bold(doc.name), frappe.bold(market)),
			title=_("Tax Template In Use"),
		)


def validate_shipping_rule(doc, method=None):
	"""Refuse to drop a market country from the store Shipping Rule."""
	if (
		frappe.flags.in_patch
		or frappe.flags.in_migrate
		or doc.is_new()
		or not doc.has_value_changed("countries")
		or doc.name != frappe.db.get_single_value("Commera Settings", "shipping_rule")
		or has_delivery_options()
	):
		return
	shipped = {row.country for row in doc.countries}
	before = doc.get_doc_before_save()
	old = {row.country for row in before.countries} if before else set()
	if shipped == old:
		return
	for country, market in get_all_market_countries():
		if shipped and country not in shipped and (not old or country in old):
			frappe.throw(
				_(
					"Shipping Rule {0} is the store delivery rule, and market {1} includes {2}. Keep {2} in"
					" its countries, or remove it from the market first."
				).format(frappe.bold(doc.name), frappe.bold(market), frappe.bold(country)),
				title=_("Shipping Rule In Use"),
			)


def get_countries_without_delivery(shipping_rule: str | None, countries: list[str]) -> list[str]:
	# Carrier coverage depends on a live quote. Configuration cannot prove a country is unreachable.
	if not shipping_rule or has_delivery_options():
		return []
	shipped = frappe.get_all(
		"Shipping Rule Country",
		filters={"parent": shipping_rule, "parenttype": "Shipping Rule"},
		pluck="country",
	)
	return [country for country in countries if shipped and country not in shipped]


def get_market_countries(market: str) -> list[str]:
	return frappe.get_all(
		"Commera Market Country", filters={"parent": market, "parenttype": MARKET_DOCTYPE}, pluck="country"
	)


def get_all_market_countries() -> list[tuple[str, str]]:
	"""(country, market name) for every market."""
	row, market = DocType("Commera Market Country"), DocType(MARKET_DOCTYPE)
	return (
		frappe.qb.from_(row)
		.join(market)
		.on(row.parent == market.name)
		.select(row.country, market.market_name)
		.where(row.parenttype == MARKET_DOCTYPE)
		.where(market.enabled == 1)
		.run()
	)
