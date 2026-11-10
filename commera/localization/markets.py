"""Markets: groups of countries with their own languages.
The primary market is the store itself: it takes every country that no other market claims."""

import re
from dataclasses import dataclass

import frappe
from frappe.query_builder import DocType

from commera.localization.languages import Language, StorefrontLanguages

MARKET_DOCTYPE = "Commera Market"
PRIMARY_MARKET = "primary"
CACHE_KEY = "commera_markets"
PRICE_FIELDS = ("sale_price_list", "compare_at_price_list", "currency")
COUNTRY_CODE = re.compile(r"[A-Za-z]{2}")
# A base language, with an optional four-letter script: `pt`, `zh-Hans`. Never a region.
MARKET_LANGUAGE = re.compile(r"[a-z]{2,3}(?:-[a-z]{4})?", re.IGNORECASE)


@dataclass(frozen=True)
class Market:
	handle: str
	title: str
	enabled: bool
	default_language: Language
	# The default language first.
	languages: tuple[Language, ...]
	# Lowercase ISO codes. The primary market lists none: it takes every unclaimed country.
	countries: tuple[str, ...]
	# None in the primary market: it reads the store's, which may change mid-request.
	sale_price_list: str | None = None
	compare_at_price_list: str | None = None
	currency: str | None = None

	@property
	def is_primary(self) -> bool:
		return self.handle == PRIMARY_MARKET

	def find_language(self, code: str | None) -> Language | None:
		code = (code or "").lower()
		return next((language for language in self.languages if language.code.lower() == code), None)

	def as_dict(self) -> dict:
		return {
			"handle": self.handle,
			"title": self.title,
			"is_primary": self.is_primary,
			"default_language": self.default_language.code,
			"languages": [language.code for language in self.languages],
			"countries": [country.upper() for country in self.countries],
			"currency": self.currency or get_default_currency(),
		}


class StorefrontMarkets:
	"""The primary market and the secondary markets a shopper may open.
	With `include_hidden`, also disabled markets and unpublished languages, for admin previews."""

	def __init__(self, languages: StorefrontLanguages, rows: list[dict], include_hidden: bool = False):
		self.languages = languages
		self.include_hidden = include_hidden
		visible = languages.configured if include_hidden else languages.published
		self.primary = Market(
			handle=PRIMARY_MARKET,
			title=get_primary_market_title(),
			enabled=True,
			default_language=languages.default,
			languages=tuple(visible),
			countries=(),
		)
		self.secondary = [
			market
			for row in rows
			if (market := self.build_market(row)) and (market.enabled or include_hidden)
		]

	@classmethod
	def load(cls, include_hidden: bool = False) -> "StorefrontMarkets":
		return cls(StorefrontLanguages.load(), get_market_rows(), include_hidden)

	@property
	def all(self) -> list[Market]:
		return [self.primary, *self.secondary]

	def find(self, handle: str | None) -> Market | None:
		handle = (handle or "").lower()
		return next((market for market in self.all if market.handle == handle), None)

	def for_country(self, code: str | None) -> Market:
		"""The market that claims the country `code`, else the primary market."""
		code = normalize_country(code) or ""
		return next((market for market in self.secondary if code in market.countries), self.primary)

	def match_prefix(self, segment: str) -> tuple[Market, Language, str] | None:
		"""The market, language and country of a `<language>-<country>` path segment."""
		language_code, _hyphen, country = (segment or "").lower().rpartition("-")
		market = self.for_country(country) if len(country) == 2 else None
		if market and not market.is_primary and (language := market.find_language(language_code)):
			return market, language, country
		return None

	def prefix(self, market: Market, language: Language, country: str | None = None) -> str:
		"""The URL prefix of `language` in `market`. A secondary market prefix names one of its countries."""
		if market.is_primary:
			return self.languages.prefix(language)
		country = (country or "").lower()
		country = country if country in market.countries else market.countries[0]
		return f"/{language.code.lower()}-{country}"

	def market_prefixes(self) -> list[tuple[Market, Language, str, str]]:
		"""(market, language, country, prefix) of every secondary market URL root."""
		return [
			(market, language, country, self.prefix(market, language, country))
			for market in self.secondary
			for language in market.languages
			for country in market.countries
		]

	@property
	def prefix_codes(self) -> tuple[str, ...]:
		"""Every first path segment that names a language or a market locale, in code order."""
		segments = {prefix[1:] for *_rest, prefix in self.market_prefixes()}
		return tuple(sorted({*self.languages.prefix_codes, *segments}))

	def build_market(self, row: dict) -> Market | None:
		languages = [lang for code in row["languages"] if (lang := self.find_language(code))]
		default = self.find_language(row["default_language"])
		if default:
			languages = [default, *(language for language in languages if language != default)]
		if not languages or not row["countries"]:
			return None
		return Market(
			handle=row["name"],
			title=row["market_name"],
			enabled=bool(row["enabled"]),
			default_language=languages[0],
			languages=tuple(languages),
			countries=tuple(row["countries"]),
			sale_price_list=row["sale_price_list"],
			compare_at_price_list=row["compare_at_price_list"],
			currency=row["currency"] or get_default_currency(),
		)

	def find_language(self, code: str | None) -> Language | None:
		# Regional rows saved before they were refused have no valid hreflang.
		return self.languages.find(code, self.include_hidden) if is_market_language(code) else None


def is_market_language(code: str | None) -> bool:
	return bool(code and MARKET_LANGUAGE.fullmatch(code))


def market_hreflang(language: Language, country: str) -> str:
	"""`<language>-<COUNTRY>`, with a script in title case: `zh-Hans-AE`."""
	base, _hyphen, script = language.code.partition("-")
	return "-".join(part for part in (base.lower(), script.title(), country.upper()) if part)


def normalize_country(value) -> str | None:
	"""`value` as a lowercase ISO code, or None. `_country` comes from the request: any type."""
	return value.lower() if isinstance(value, str) and COUNTRY_CODE.fullmatch(value) else None


def find_market_by_prefix(code: str) -> str | None:
	"""The name of the market, enabled or not, with a URL `/<language>-<country>/` equal to `code`."""
	code = (code or "").lower()
	for row in get_market_rows():
		if any(
			f"{language}-{country}" == code
			for language in row["languages"]
			if is_market_language(language)
			for country in row["countries"]
		):
			return row["market_name"]
	return None


def get_market_rows() -> list[dict]:
	return frappe.cache.get_value(CACHE_KEY, generator=fetch_market_rows)


def clear_market_cache():
	"""Clear now, and again once the transaction ends: a request in between may cache the old rows."""
	frappe.cache.delete_value(CACHE_KEY)
	frappe.db.after_commit.add(delete_cached_rows)
	frappe.db.after_rollback.add(delete_cached_rows)


def delete_cached_rows():
	frappe.cache.delete_value(CACHE_KEY)


def fetch_market_rows() -> list[dict]:
	if not frappe.db.table_exists(MARKET_DOCTYPE):
		return []
	fields = ["name", "market_name", "enabled", "default_language", *PRICE_FIELDS]
	rows = frappe.get_all(MARKET_DOCTYPE, fields=fields, order_by="creation")
	countries = get_child_values("Commera Market Country", "country")
	languages = get_child_values("Commera Market Language", "language")
	for row in rows:
		row["countries"] = [code for code in countries.get(row.name, []) if code]
		row["languages"] = languages.get(row.name, [])
	return [dict(row) for row in rows]


def get_child_values(doctype: str, fieldname: str) -> dict[str, list[str]]:
	child = DocType(doctype)
	query = frappe.qb.from_(child).select(child.parent).orderby(child.parent).orderby(child.idx)
	if fieldname == "country":
		country = DocType("Country")
		query = query.left_join(country).on(country.name == child.country).select(country.code)
	else:
		query = query.select(child[fieldname])
	values = {}
	for parent, value in query.run():
		values.setdefault(parent, []).append((value or "").lower())
	return values


def get_default_currency() -> str:
	from commera.utils import get_store_currency

	return get_store_currency()


def get_primary_market_title() -> str:
	from commera.utils import get_store_company

	company = get_store_company()
	return (company and frappe.get_cached_value("Company", company, "country")) or frappe._("Primary market")


def get_store_country() -> str | None:
	"""The lowercase ISO code of the store company's country."""
	from commera.utils import get_store_company

	company = get_store_company()
	country = frappe.get_cached_value("Company", company, "country") if company else None
	return frappe.get_cached_value("Country", country, "code") if country else None
