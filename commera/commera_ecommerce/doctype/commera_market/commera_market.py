# Copyright (c) 2026, hussain@buildwithhussain.com and contributors
# For license information, please see license.txt

import re

import frappe
from erpnext.stock.doctype.price_list.price_list import validate_price_list_country
from frappe import _
from frappe.model.document import Document
from frappe.query_builder import DocType
from frappe.website.utils import clear_cache as clear_website_cache

from commera.localization.languages import StorefrontLanguages
from commera.localization.market_setup import MarketStoreFit, market_field, validates_field
from commera.localization.markets import PRIMARY_MARKET, clear_market_cache, is_market_language
from commera.search.price_sync import rebuild_if_market_prices_change
from commera.search.translations import reindex_market_records

HANDLE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Orders and carts keep the market handle as text, so Frappe's link check does not see them. A link
# field cannot hold it: they store "primary" for the store's own prices.
MARKET_REFERENCES = (
	("Sales Order", "commera_market"),
	("Quotation", "commera_market"),
	("Commera Cart", "market"),
)


class CommeraMarket(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from commera.commera_ecommerce.doctype.commera_market_country.commera_market_country import (
			CommeraMarketCountry,
		)
		from commera.commera_ecommerce.doctype.commera_market_language.commera_market_language import (
			CommeraMarketLanguage,
		)

		compare_at_price_list: DF.Link | None
		countries: DF.Table[CommeraMarketCountry]
		currency: DF.Link | None
		default_language: DF.Link
		enabled: DF.Check
		handle: DF.Data | None
		languages: DF.Table[CommeraMarketLanguage]
		market_name: DF.Data
		sale_price_list: DF.Link
		tax_template: DF.Link | None
	# end: auto-generated types

	def autoname(self):
		self.handle = self.handle or make_handle(self.market_name)
		self.name = self.handle

	def validate(self):
		if not self.enabled:
			self.currency = get_price_list_currency(self.sale_price_list)
		if frappe.flags.in_patch or frappe.flags.in_migrate:
			return
		full = self.is_new() or self.is_enabled_now()
		if full or self.has_fields_changed("handle"):
			self.validate_handle()
		if full or self.has_fields_changed("countries"):
			self.validate_countries()
		if full or self.has_fields_changed("languages", "default_language", "countries"):
			self.validate_languages()
		# A disabled market sells nothing, so it need not fit the store setup yet.
		if self.enabled:
			self.validate_store_fit(full)

	def validate_store_fit(self, full: bool):
		before = self.get_doc_before_save()
		if full or self.has_fields_changed("sale_price_list", "compare_at_price_list"):
			self.validate_price_lists(full=full)
		if full or self.has_fields_changed("sale_price_list", "countries"):
			self.validate_price_list_countries()
		fit = MarketStoreFit(self)
		if full or self.has_fields_changed("tax_template"):
			fit.validate_tax_template()
		if full or (self.has_fields_changed("sale_price_list") and self.currency != before.currency):
			fit.validate_invoice_currency()
		if full or self.has_fields_changed("countries"):
			old = set() if full else {row.country for row in before.countries}
			fit.validate_delivery_countries([row.country for row in self.countries if row.country not in old])

	def is_enabled_now(self) -> bool:
		before = self.get_doc_before_save()
		return bool(self.enabled and before and not before.enabled)

	def has_fields_changed(self, *fields) -> bool:
		return any(
			not self.is_child_table_same(field)
			if self.meta.get_field(field).fieldtype == "Table"
			else self.has_value_changed(field)
			for field in fields
		)

	def before_save(self):
		self.reinsert_changed_countries()

	def on_update(self):
		refresh_market_surfaces()
		rebuild_if_market_prices_change(self.get_doc_before_save(), self)

	def on_trash(self):
		self.validate_not_in_use()
		rebuild_if_market_prices_change(self, None)
		reindex_market_records(self.name)
		# An export would list them under a market an import refuses.
		frappe.db.delete("Content Translation", {"market": self.name})

	def after_delete(self):
		# robots.txt lists the market URLs it reads, so the row must be gone.
		refresh_market_surfaces()

	def validate_not_in_use(self):
		"""Without its market, an order or cart is repriced in the store currency, and a new market with
		the same handle would take it over."""
		for doctype, fieldname in MARKET_REFERENCES:
			if name := frappe.db.get_value(doctype, {fieldname: self.name}):
				frappe.throw(
					_("Market {0} is used by {1} {2}. Disable the market instead of deleting it.").format(
						frappe.bold(self.market_name), _(doctype), frappe.bold(name)
					),
					title=_("Market In Use"),
					exc=frappe.LinkExistsError,
				)

	@validates_field("handle")
	def validate_handle(self):
		if not HANDLE_PATTERN.match(self.handle or "") or self.handle == PRIMARY_MARKET:
			frappe.throw(
				_("Handle {0} must use lowercase letters, digits and hyphens, and not be {1}.").format(
					frappe.bold(self.handle or ""), frappe.bold(PRIMARY_MARKET)
				),
				title=_("Invalid Handle"),
			)

	@validates_field("countries")
	def validate_countries(self):
		countries = [row.country for row in self.countries]
		if not countries:
			frappe.throw(_("Add at least one country."), title=_("No Countries"))
		if duplicates := sorted({country for country in countries if countries.count(country) > 1}):
			frappe.throw(_("{0} is listed more than once.").format(frappe.bold(duplicates[0])))
		for country in countries:
			if len(get_country_code(country)) != 2:
				frappe.throw(_("Country {0} has no two-letter code.").format(frappe.bold(country)))
		for country, market in self.get_countries_in_other_markets(countries):
			throw_country_taken(country, market)

	def get_countries_in_other_markets(self, countries: list[str]) -> list[tuple[str, str]]:
		"""For the error message only. The unique index on the country column refuses races."""
		row = DocType("Commera Market Country")
		return (
			frappe.qb.from_(row)
			.select(row.country, row.parent)
			.where(row.parenttype == self.doctype)
			.where(row.country.isin(countries))
			.where(row.parent != (self.name or ""))
			.run()
		)

	@validates_field("languages")
	def validate_languages(self):
		languages = StorefrontLanguages.load()
		self.validate_default_language(languages)
		codes = [row.language for row in self.languages]
		saved = self.get_saved_languages()
		for code in codes:
			# Saved rows stay valid, so an older market can still drop them or be disabled.
			if code not in saved:
				self.validate_published(languages, code)
				self.validate_no_region(code)
			if codes.count(code) > 1:
				frappe.throw(_("Language {0} is listed more than once.").format(frappe.bold(code)))
		self.validate_prefixes(languages, codes)

	def validate_default_language(self, languages: StorefrontLanguages):
		"""The default is one of the languages. An unpublished default may stay, not be chosen or re-added."""
		listed = any(row.language == self.default_language for row in self.languages)
		chosen = not listed or self.has_value_changed("default_language")
		if chosen and not languages.find(self.default_language):
			frappe.throw(
				_("Default language {0} is not published. Choose a published default language.").format(
					frappe.bold(self.default_language)
				),
				title=_("Unpublished Language"),
			)
		if not listed:
			self.append("languages", {"language": self.default_language})

	def validate_published(self, languages: StorefrontLanguages, code: str):
		if not languages.find(code):
			frappe.throw(
				_("Language {0} is not a published storefront language.").format(frappe.bold(code)),
				title=_("Unpublished Language"),
			)

	def get_saved_languages(self) -> set[str]:
		before = self.get_doc_before_save()
		return set() if not before or self.is_enabled_now() else {row.language for row in before.languages}

	def validate_no_region(self, code: str):
		"""The hreflang of a market URL is `<language>-<COUNTRY>`. pt-BR in Portugal has no valid tag."""
		if not is_market_language(code):
			frappe.throw(
				_(
					"Language {0} names a region. A market takes its region from its countries, so its"
					" languages must be base languages such as {1}, or a base language with a script"
					" such as zh-Hans. Publish {1} and add it here. The primary market serves {0}."
				).format(frappe.bold(code), frappe.bold(code.partition("-")[0])),
				title=_("Regional Language"),
			)

	@validates_field("compare_at_price_list")
	def validate_price_lists(self, full=True):
		"""The market sells in the sale price list's currency; Commera converts no prices."""
		for fieldname in ("sale_price_list", "compare_at_price_list"):
			with market_field(fieldname):
				if (full or self.has_value_changed(fieldname)) and (price_list := self.get(fieldname)):
					validate_selling_price_list(price_list, _(self.meta.get_label(fieldname)))
		self.currency = get_price_list_currency(self.sale_price_list)
		compare_at_currency = get_price_list_currency(self.compare_at_price_list)
		before = self.get_doc_before_save()
		was_matching = (
			not before
			or not before.compare_at_price_list
			or get_price_list_currency(before.compare_at_price_list) == before.currency
		)
		if self.compare_at_price_list and compare_at_currency != self.currency and (full or was_matching):
			frappe.throw(
				_(
					"Compare-at Price List {0} is in {1}, but the Sale Price List is in {2}. Use one currency."
				).format(frappe.bold(self.compare_at_price_list), compare_at_currency, self.currency),
				title=_("Currency Mismatch"),
			)

	@validates_field("sale_price_list")
	def validate_price_list_countries(self):
		"""ERPNext refuses a sale to an address outside the sale list's countries."""
		before = self.get_doc_before_save()
		old = {row.country for row in before.countries} if before and before.enabled else set()
		old_list_countries = (
			set(
				frappe.get_all(
					"Price List Country", filters={"parent": before.sale_price_list}, pluck="country"
				)
			)
			if before and before.enabled
			else set()
		)
		for row in self.countries:
			if row.country in old and old_list_countries and row.country not in old_list_countries:
				continue
			if row.country not in old or self.has_value_changed("sale_price_list"):
				validate_price_list_country(self.sale_price_list, row.country)

	def reinsert_changed_countries(self):
		"""Frappe updates kept rows one by one, so a swap of two countries breaks the unique index midway.
		As new rows, Frappe deletes them with the removed rows first, then inserts them under their names."""
		before = self.get_doc_before_save()
		saved = {row.name: row.country for row in before.countries} if before else {}
		for row in self.countries:
			if row.name in saved and saved[row.name] != row.country:
				row.set("__islocal", 1)

	@validates_field("urls")
	def validate_prefixes(self, languages: StorefrontLanguages, codes: list[str]):
		"""`/pt-br/` would name both Portuguese in Brazil and the language pt-BR, and share its hreflang."""
		for code in codes:
			for row in self.countries:
				prefix = f"{code}-{get_country_code(row.country)}"
				if languages.find(prefix, include_unpublished=True):
					frappe.throw(
						_("The URL /{0}/ of {1} in {2} is already a storefront language.").format(
							prefix.lower(), frappe.bold(code), frappe.bold(row.country)
						),
						title=_("URL Taken"),
					)


def throw_country_taken(country: str, market: str | None, exc=frappe.ValidationError):
	if market:
		message = _("{0} is already in market {1}. A country belongs to one market only.")
	else:
		message = _("{0} is already in another market. A country belongs to one market only.")
	# Name the market as admins see it; its record name is only the handle.
	title = market and (frappe.db.get_value("Commera Market", market, "market_name") or market)
	frappe.throw(
		message.format(frappe.bold(country), frappe.bold(title)),
		title=_("Country In Another Market"),
		exc=exc,
	)


def validate_selling_price_list(price_list: str, label: str):
	"""ERPNext refuses a disabled or a buying-only price list in a sale."""
	enabled, selling = frappe.db.get_value("Price List", price_list, ["enabled", "selling"]) or (0, 0)
	if not selling:
		message = _("{0} {1} is not a selling price list.")
	elif not enabled:
		message = _("{0} {1} is disabled.")
	else:
		return
	frappe.throw(message.format(label, frappe.bold(price_list)), title=_("Invalid Price List"))


def get_price_list_currency(price_list: str | None) -> str | None:
	return frappe.get_cached_value("Price List", price_list, "currency") if price_list else None


def refresh_market_surfaces():
	from commera.migrate import setup_robots_txt

	clear_market_cache()
	# Cached guest pages carry the old hreflang tags.
	clear_website_cache()
	setup_robots_txt()


def make_handle(title: str | None) -> str:
	return re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")


def get_country_code(country: str) -> str:
	return (frappe.db.get_value("Country", country, "code") or "").lower()
