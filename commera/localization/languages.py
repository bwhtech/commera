from dataclasses import asdict, dataclass
from functools import lru_cache

import frappe
from babel import Locale, UnknownLocaleError
from babel.core import get_global
from frappe.utils.jinja_globals import is_rtl

FALLBACK_LANGUAGE = "en"
MAX_STOREFRONT_LANGUAGES = 20


@dataclass(frozen=True)
class Language:
	code: str
	name: str
	endonym: str
	direction: str

	@classmethod
	def from_code(cls, code: str) -> "Language":
		name, endonym = get_display_names(code)
		return cls(
			code=code,
			name=name,
			endonym=endonym,
			direction="rtl" if is_rtl_language(code) else "ltr",
		)

	def as_dict(self) -> dict:
		return asdict(self)

	def og_locale(self, market_country: str | None = None, store_country: str | None = None) -> str:
		"""Open Graph `ll_CC`. The region is the code's own (`pt-BR`), else the market country, else the
		store country when people there use the language, else the CLDR likely one."""
		region = (
			get_code_region(self.code)
			or market_country
			or (store_country if is_used_in(self.code, store_country) else None)
			or get_likely_region(self.code)
		)
		base = self.code.partition("-")[0].lower()
		return f"{base}_{region.upper()}" if region else base


class StorefrontLanguages:
	"""The default language and the published and unpublished languages from Commera Settings."""

	def __init__(self, default_code: str, rows: list[tuple[str, bool]]):
		self.default = Language.from_code(default_code)
		self.published = [self.default]
		self.unpublished = []
		for code, published in rows:
			if code == default_code or self.find(code, include_unpublished=True):
				continue
			(self.published if published else self.unpublished).append(Language.from_code(code))

	@classmethod
	def load(cls) -> "StorefrontLanguages":
		return cls.from_settings(frappe.get_cached_doc("Commera Settings"))

	@classmethod
	def from_settings(cls, settings) -> "StorefrontLanguages":
		rows = [(row.language, bool(row.published)) for row in settings.get("storefront_languages") or []]
		return cls(get_default_language_code(settings), rows)

	@property
	def configured(self) -> list[Language]:
		"""Published and unpublished languages, default first."""
		return self.published + self.unpublished

	@property
	def prefix_codes(self) -> tuple[str, ...]:
		"""The codes of all configured languages, published or not, in code order."""
		return tuple(sorted(language.code for language in self.configured))

	def prefix(self, language: Language) -> str:
		"""The URL prefix of `language`. The default language has none."""
		return "" if language == self.default else f"/{language.code.lower()}"

	def find(self, code: str | None, include_unpublished: bool = False) -> Language | None:
		if not code:
			return None
		languages = self.configured if include_unpublished else self.published
		code = code.lower()
		return next((language for language in languages if language.code.lower() == code), None)


def get_default_language_code(settings) -> str:
	return (
		settings.get("default_storefront_language")
		or frappe.get_system_settings("language")
		or FALLBACK_LANGUAGE
	)


def seed_storefront_languages(default: str, codes: tuple[str, ...]):
	"""Publish `codes` on a store with no language settings yet.
	Writes rows directly: a Commera Settings save also checks unrelated required fields."""
	if frappe.db.exists("Commera Storefront Language", {"parent": "Commera Settings"}):
		return

	frappe.db.set_single_value("Commera Settings", "default_storefront_language", default)
	codes = [code for code in codes if frappe.db.exists("Language", code)]
	for idx, code in enumerate(codes, start=1):
		frappe.get_doc(
			{
				"doctype": "Commera Storefront Language",
				"parent": "Commera Settings",
				"parenttype": "Commera Settings",
				"parentfield": "storefront_languages",
				"idx": idx,
				"language": code,
				"published": 1,
			}
		).db_insert()
	frappe.clear_document_cache("Commera Settings", "Commera Settings")


def is_rtl_language(code: str) -> bool:
	# Frappe keeps its right-to-left set inside is_rtl(), which reads frappe.local.lang.
	previous = getattr(frappe.local, "lang", None)
	frappe.local.lang = code
	try:
		return is_rtl()
	finally:
		frappe.local.lang = previous


@lru_cache(maxsize=64)
def get_display_names(code: str) -> tuple[str, str]:
	"""English name and native name (endonym) of a Frappe language code."""
	locale = parse_locale(code)
	if not locale:
		name = frappe.db.get_value("Language", code, "language_name") or code
		return name, name
	return locale.get_display_name("en"), locale.get_display_name(locale)


@lru_cache(maxsize=64)
def get_code_region(code: str) -> str | None:
	"""The region `code` names itself: `BR` in `pt-BR`."""
	locale = parse_locale(code)
	return locale.territory if locale and is_region(locale.territory) else None


@lru_cache(maxsize=256)
def is_used_in(code: str, country: str | None) -> bool:
	"""Whether CLDR lists `code` as a language of `country`. `zh-Hant` must match its script."""
	locale = parse_locale(code)
	if not locale or not is_region(country):
		return False
	used = get_global("territory_languages").get(country.upper(), {})
	if locale.script and f"{locale.language}_{locale.script}" in used:
		return True
	return locale.language in used and (
		not locale.script or locale.script == get_likely_script(locale.language)
	)


@lru_cache(maxsize=64)
def get_likely_region(code: str) -> str | None:
	"""The region CLDR finds most likely: `en` is in US, `zh-Hant` in TW."""
	locale = parse_locale(code)
	if not locale:
		return None
	likely = get_global("likely_subtags")
	key = f"{locale.language}_{locale.script}" if locale.script else locale.language
	region = (likely.get(key) or likely.get(locale.language, "")).rpartition("_")[2]
	return region if is_region(region) else None


def get_likely_script(language: str) -> str | None:
	# `zh` alone is written in Hans: zh_Hans_CN.
	parts = get_global("likely_subtags").get(language, "").split("_")
	return parts[1] if len(parts) == 3 else None


def parse_locale(code: str) -> Locale | None:
	try:
		return Locale.parse(code, sep="-")
	except (UnknownLocaleError, ValueError):
		return None


def is_region(value: str | None) -> bool:
	return bool(value and len(value) == 2 and value.isalpha())
