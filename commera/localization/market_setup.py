"""A market sells through ERPNext records it does not own: its price lists, its tax template, the
store Shipping Rule and the company accounts. ERPNext checks them only in a shopper's checkout, so
Commera checks them when the merchant saves the market, and again when one of these records changes."""

from contextlib import contextmanager
from functools import wraps

import frappe
from frappe import _
from frappe.query_builder import DocType

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
		"""ERPNext invoices a shopper against the company receivable account. It accepts an invoice in
		another currency only with this Accounts Settings option, and the payment is captured by then."""
		company_currency = get_store_currency(self.company)
		if self.market.currency in (None, company_currency) or frappe.db.get_single_value(
			"Accounts Settings", MULTI_CURRENCY_FIELD
		):
			return
		frappe.throw(
			_(
				"Market {0} sells in {1}, but {2} keeps its accounts in {3}. ERPNext can invoice orders in {1}"
				" only when {4} is on in Accounts Settings. Turn it on, or use a price list in {3}."
			).format(
				*self.bold(self.market.market_name, self.market.currency, self.company, company_currency),
				frappe.bold(_(frappe.get_meta("Accounts Settings").get_label(MULTI_CURRENCY_FIELD).strip())),
			),
			title=_("Currency Cannot Be Invoiced"),
		)

	@validates_field("countries")
	def validate_delivery_countries(self):
		"""ERPNext applies the store Shipping Rule to every cart and refuses an address outside its countries."""
		countries = [row.country for row in self.market.countries]
		if missing := get_countries_without_delivery(self.shipping_rule, countries):
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
	"""A new store company or Shipping Rule must still fit every market."""
	if settings.is_new() or not (
		settings.has_value_changed("company") or settings.has_value_changed("shipping_rule")
	):
		return
	for name in frappe.get_all(MARKET_DOCTYPE, pluck="name"):
		MarketStoreFit(frappe.get_doc(MARKET_DOCTYPE, name), settings).validate()


def validate_price_list(doc, method=None):
	"""Refuse a Price List change that a market's checkout would fail on."""
	# Before the schema sync no market has a price list.
	if doc.is_new() or not frappe.db.has_column(MARKET_DOCTYPE, "sale_price_list"):
		return
	markets = frappe.get_all(
		MARKET_DOCTYPE,
		or_filters={"sale_price_list": doc.name, "compare_at_price_list": doc.name},
		fields=["name", "market_name", "sale_price_list"],
	)
	if not markets:
		return
	if doc.has_value_changed("currency"):
		throw_price_list_in_use(
			_("Price List {0} sets the prices of market {1}, so its currency cannot change."), doc, markets[0]
		)
	if not (doc.enabled and doc.selling):
		throw_price_list_in_use(
			_(
				"Price List {0} sets the prices of market {1}, so it must stay enabled and selling."
				" Choose another price list for the market first."
			),
			doc,
			markets[0],
		)
	validate_price_list_countries(doc, [market for market in markets if market.sale_price_list == doc.name])


def validate_price_list_countries(doc, markets: list[dict]):
	"""ERPNext refuses a sale to an address outside the sale list's countries. No countries: all."""
	if not (countries := {row.country for row in doc.countries}):
		return
	for market in markets:
		if missing := [country for country in get_market_countries(market.name) if country not in countries]:
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
	if not (doc.disabled or doc.company != get_store_company()):
		return
	if market := frappe.db.get_value(MARKET_DOCTYPE, {"tax_template": doc.name}, "market_name"):
		frappe.throw(
			_(
				"Tax template {0} sets the taxes of market {1}, so it must stay enabled in the store company."
				" Choose another template for the market first."
			).format(frappe.bold(doc.name), frappe.bold(market)),
			title=_("Tax Template In Use"),
		)


def validate_shipping_rule(doc, method=None):
	"""Refuse to drop a market country from the store Shipping Rule."""
	if doc.is_new() or doc.name != frappe.db.get_single_value("Commera Settings", "shipping_rule"):
		return
	shipped = {row.country for row in doc.countries}
	for country, market in get_all_market_countries():
		if shipped and country not in shipped:
			frappe.throw(
				_(
					"Shipping Rule {0} is the store delivery rule, and market {1} includes {2}. Keep {2} in"
					" its countries, or remove it from the market first."
				).format(frappe.bold(doc.name), frappe.bold(market), frappe.bold(country)),
				title=_("Shipping Rule In Use"),
			)


def validate_accounts_settings(doc, method=None):
	"""Refuse to turn off multi-currency invoices while a market sells in another currency."""
	if doc.get(MULTI_CURRENCY_FIELD) or not doc.has_value_changed(MULTI_CURRENCY_FIELD):
		return
	if not frappe.db.has_column(MARKET_DOCTYPE, "currency"):
		return
	currency = get_store_currency()
	if market := frappe.db.get_value(MARKET_DOCTYPE, {"currency": ("!=", currency)}, "market_name"):
		frappe.throw(
			_(
				"Market {0} sells in another currency than {1}, so ERPNext needs {2} to invoice its orders."
				" Change the market's price lists to {1} first."
			).format(
				frappe.bold(market),
				frappe.bold(currency),
				frappe.bold(_(doc.meta.get_label(MULTI_CURRENCY_FIELD).strip())),
			),
			title=_("Market Needs Multi-Currency Invoices"),
		)


def get_countries_without_delivery(shipping_rule: str | None, countries: list[str]) -> list[str]:
	if not shipping_rule:
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
		.run()
	)
