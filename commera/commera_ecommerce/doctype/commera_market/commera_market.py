# Copyright (c) 2026, hussain@buildwithhussain.com and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder import DocType
from frappe.website.utils import clear_cache as clear_website_cache

from commera.localization.languages import StorefrontLanguages
from commera.localization.markets import PRIMARY_MARKET, clear_market_cache, is_market_language
from commera.search.price_sync import rebuild_if_market_prices_change
from commera.search.translations import reindex_market_records

HANDLE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


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
	# end: auto-generated types

	def autoname(self):
		self.handle = self.handle or make_handle(self.market_name)
		self.name = self.handle

	def validate(self):
		self.validate_handle()
		self.validate_countries()
		self.validate_languages()
		self.validate_price_lists()

	def before_save(self):
		self.reinsert_changed_countries()

	def on_update(self):
		refresh_market_surfaces()
		rebuild_if_market_prices_change(self.get_doc_before_save(), self)

	def on_trash(self):
		rebuild_if_market_prices_change(self, None)
		reindex_market_records(self.name)
		# An export would list them under a market an import refuses.
		frappe.db.delete("Content Translation", {"market": self.name})
		refresh_market_surfaces()

	def validate_handle(self):
		if not HANDLE_PATTERN.match(self.handle or "") or self.handle == PRIMARY_MARKET:
			frappe.throw(
				_("Handle {0} must use lowercase letters, digits and hyphens, and not be {1}.").format(
					frappe.bold(self.handle or ""), frappe.bold(PRIMARY_MARKET)
				),
				title=_("Invalid Handle"),
			)

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
		return {row.language for row in before.languages} if before else set()

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

	def validate_price_lists(self):
		"""The market sells in the sale price list's currency; Commera converts no prices."""
		for fieldname in ("sale_price_list", "compare_at_price_list"):
			if (price_list := self.get(fieldname)) and not frappe.get_cached_value(
				"Price List", price_list, "selling"
			):
				frappe.throw(
					_("{0} {1} is not a selling price list.").format(
						_(self.meta.get_label(fieldname)), frappe.bold(price_list)
					),
					title=_("Invalid Price List"),
				)
		self.currency = get_price_list_currency(self.sale_price_list)
		compare_at_currency = get_price_list_currency(self.compare_at_price_list)
		if self.compare_at_price_list and compare_at_currency != self.currency:
			frappe.throw(
				_(
					"Compare-at Price List {0} is in {1}, but the Sale Price List is in {2}. Use one currency."
				).format(frappe.bold(self.compare_at_price_list), compare_at_currency, self.currency),
				title=_("Currency Mismatch"),
			)

	def reinsert_changed_countries(self):
		"""Frappe updates kept rows one by one, so a swap of two countries breaks the unique index midway.
		As new rows, Frappe deletes them with the removed rows first, then inserts them under their names."""
		before = self.get_doc_before_save()
		saved = {row.name: row.country for row in before.countries} if before else {}
		for row in self.countries:
			if row.name in saved and saved[row.name] != row.country:
				row.set("__islocal", 1)

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
	frappe.throw(
		message.format(frappe.bold(country), frappe.bold(market)),
		title=_("Country In Another Market"),
		exc=exc,
	)


def validate_market_price_list(doc, method=None):
	"""A market's currency is its price lists' currency, cached with the markets."""
	if doc.is_new() or not doc.has_value_changed("currency"):
		return
	# Before the schema sync no market has a price list.
	if not frappe.db.has_column("Commera Market", "sale_price_list"):
		return
	markets = frappe.get_all(
		"Commera Market",
		or_filters={"sale_price_list": doc.name, "compare_at_price_list": doc.name},
		pluck="market_name",
		limit=1,
	)
	if markets:
		frappe.throw(
			_("Price List {0} sets the prices of market {1}, so its currency cannot change.").format(
				frappe.bold(doc.name), frappe.bold(markets[0])
			),
			title=_("Price List In Use"),
		)


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
