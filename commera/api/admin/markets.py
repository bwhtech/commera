# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""The dashboard's Markets settings. Every write saves through Commera Market, so its validations run,
and answers with the saved market."""

from functools import wraps

import frappe
from frappe import _
from frappe.utils import cint

from commera.commera_ecommerce.doctype.commera_market.commera_market import market_field
from commera.localization.languages import StorefrontLanguages
from commera.localization.markets import (
	MARKET_DOCTYPE,
	PRIMARY_MARKET,
	get_primary_market_title,
	get_store_country,
)
from commera.roles import is_commera_admin
from commera.utils import get_store_company, get_store_currency

TAX_TEMPLATE_FIELD = "tax_template"
EDITABLE_FIELDS = (
	"market_name",
	"enabled",
	"default_language",
	"sale_price_list",
	"compare_at_price_list",
	TAX_TEMPLATE_FIELD,
)


def market_validation_response(action):
	@wraps(action)
	def wrapped(*args, **kwargs):
		try:
			return action(*args, **kwargs)
		except frappe.ValidationError as error:
			if not getattr(error, "field", None):
				raise
			frappe.clear_messages()
			return {"field": error.field, "message": str(error)}

	return wrapped


# Not GET-only: the dashboard reads it through createAdminCaller, which POSTs.
@frappe.whitelist()
def get_markets() -> list[dict]:
	"""The primary market first, then the other markets in the order they were made."""
	require_store_admin()
	names = frappe.get_all(MARKET_DOCTYPE, order_by="creation", pluck="name")
	return [get_primary_market(), *(as_record(frappe.get_doc(MARKET_DOCTYPE, name)) for name in names)]


@frappe.whitelist()
def get_market_choices() -> dict:
	require_store_admin()
	return {
		"countries": frappe.get_all(
			"Country", filters={"code": ["is", "set"]}, fields=["name", "code"], order_by="name"
		),
		"languages": get_language_choices(),
		"price_lists": frappe.get_all(
			"Price List", filters={"selling": 1, "enabled": 1}, fields=["name", "currency"], order_by="name"
		),
		# None before the market has a tax template field: the editor then shows no tax select.
		"tax_templates": get_tax_templates() if has_tax_template() else None,
	}


@frappe.whitelist(methods=["POST"])
@market_validation_response
def create_market(
	market_name: str,
	countries: list | str,
	languages: list | str,
	default_language: str,
	sale_price_list: str,
	handle: str | None = None,
	compare_at_price_list: str | None = None,
	tax_template: str | None = None,
	enabled: bool | int = 1,
) -> dict:
	require_store_admin()
	doc = frappe.new_doc(MARKET_DOCTYPE)
	doc.handle = (handle or "").strip() or None
	MarketChange(doc).apply(
		{
			"market_name": market_name,
			"enabled": enabled,
			"default_language": default_language,
			"sale_price_list": sale_price_list,
			"compare_at_price_list": compare_at_price_list,
			TAX_TEMPLATE_FIELD: tax_template,
			"countries": countries,
			"languages": languages,
		}
	)
	doc.insert(ignore_permissions=True)
	return as_record(doc)


@frappe.whitelist(methods=["POST"])
@market_validation_response
def update_market(handle: str, **values) -> dict:
	"""Writes only the fields sent: each control in the editor saves its own field."""
	doc = get_market_for_update(handle)
	MarketChange(doc).apply(values)
	doc.save(ignore_permissions=True)
	return as_record(doc)


@frappe.whitelist(methods=["POST"])
def delete_market(handle: str):
	doc = get_market_for_update(handle)
	frappe.delete_doc(MARKET_DOCTYPE, doc.name, ignore_permissions=True)


class MarketChange:
	"""Copies the editor's values onto a Commera Market. The doctype validates them on save."""

	def __init__(self, doc):
		self.doc = doc

	def apply(self, values: dict):
		for fieldname in EDITABLE_FIELDS:
			if fieldname in values and self.doc.meta.has_field(fieldname):
				self.doc.set(fieldname, self.coerce(fieldname, values[fieldname]))
		if "countries" in values:
			self.set_rows("countries", "country", parse_list(values["countries"]))
		if "languages" in values:
			self.set_languages(parse_list(values["languages"]))

	def coerce(self, fieldname: str, value):
		if fieldname == "enabled":
			return cint(value)
		if isinstance(value, str):
			return value.strip() or None
		return value

	def set_languages(self, codes: list[str]):
		if not codes:
			with market_field("languages"):
				frappe.throw(_("Choose at least one language."), title=_("No Languages"))
		# The doctype adds a default missing from the list back, so a dropped default hands over.
		if self.doc.default_language not in codes:
			self.doc.default_language = codes[0]
		self.set_rows("languages", "language", codes)

	def set_rows(self, fieldname: str, column: str, values: list[str]):
		"""Kept rows keep their names, so a save updates them instead of re-inserting them."""
		saved = {row.get(column): row for row in self.doc.get(fieldname)}
		self.doc.set(fieldname, [])
		for value in values:
			self.doc.append(fieldname, saved.get(value) or {column: value})


def as_record(doc) -> dict:
	return {
		"handle": doc.name,
		"is_primary": False,
		"market_name": doc.market_name,
		"enabled": cint(doc.enabled),
		"countries": [row.country for row in doc.countries],
		"default_language": doc.default_language,
		"languages": [row.language for row in doc.languages],
		"sale_price_list": doc.sale_price_list,
		"compare_at_price_list": doc.compare_at_price_list,
		"currency": doc.currency,
		TAX_TEMPLATE_FIELD: doc.get(TAX_TEMPLATE_FIELD),
	}


def get_primary_market() -> dict:
	"""The store itself: its published languages, its own price lists and every country no market has."""
	settings = frappe.get_cached_doc("Commera Settings")
	languages = StorefrontLanguages.from_settings(settings)
	country = get_store_country()
	return {
		"handle": PRIMARY_MARKET,
		"is_primary": True,
		"market_name": get_primary_market_title(),
		"enabled": 1,
		"countries": [],
		"country_code": country.upper() if country else None,
		"default_language": languages.default.code,
		"languages": [language.code for language in languages.published],
		"sale_price_list": settings.get("sale_price_list"),
		"compare_at_price_list": settings.get("default_price_list"),
		"currency": get_store_currency(),
		TAX_TEMPLATE_FIELD: None,
	}


def get_market_for_update(handle: str):
	require_store_admin()
	if handle == PRIMARY_MARKET:
		frappe.throw(
			_("The primary market is your store. Edit its prices in General and its languages in Languages."),
			title=_("Primary Market"),
		)
	return frappe.get_doc(MARKET_DOCTYPE, handle, for_update=True)


def get_language_choices() -> list[dict]:
	"""Every storefront language, default first. Only published ones can join a market."""
	languages = StorefrontLanguages.load()
	published = set(languages.published)
	return [
		{"code": language.code, "name": language.name, "published": language in published}
		for language in languages.configured
	]


def has_tax_template() -> bool:
	return frappe.get_meta(MARKET_DOCTYPE).has_field(TAX_TEMPLATE_FIELD)


def get_tax_templates() -> list[str]:
	return frappe.get_all(
		"Sales Taxes and Charges Template",
		filters={"company": get_store_company(), "disabled": 0},
		order_by="name",
		pluck="name",
	)


def parse_list(value) -> list[str]:
	values = frappe.parse_json(value) if isinstance(value, str) else value
	return [item for item in values or [] if item]


def require_store_admin():
	if not is_commera_admin():
		frappe.throw(_("Only store administrators can manage markets."), frappe.PermissionError)
