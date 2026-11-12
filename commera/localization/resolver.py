from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import frappe
from frappe.utils.caching import request_cache

from commera.localization.languages import Language, StorefrontLanguages
from commera.localization.markets import Market, StorefrontMarkets, normalize_country
from commera.roles import is_commera_admin


@dataclass(frozen=True)
class Localization:
	language: Language
	# The store's default language: the language of the source content.
	default_language: Language
	available_languages: tuple[Language, ...]
	root_prefix: str
	# Every configured code, published or not: a client's url() strips each one as a prefix.
	prefix_codes: tuple[str, ...] = ()
	market: Market | None = None
	available_markets: tuple[Market, ...] = ()
	# The lowercase ISO code the URL or `_country` named.
	country: str | None = None

	def as_dict(self) -> dict:
		return {
			"language": self.language.as_dict(),
			"default_language": self.default_language.as_dict(),
			"available_languages": [language.as_dict() for language in self.available_languages],
			"root_prefix": self.root_prefix,
			"prefix_codes": list(self.prefix_codes),
			"market": self.market.as_dict() if self.market else None,
			"available_markets": [market.as_dict() for market in self.available_markets],
			"country": self.country.upper() if self.country else None,
		}


@dataclass(frozen=True)
class LocalePrefix:
	"""What the first path segment names: `/<language>/` or a market's `/<language>-<country>/`."""

	market: Market
	language: Language
	country: str | None = None


def resolve(
	path: str, lang: str | None = None, include_unpublished: bool = False, country: str | None = None
) -> tuple[Localization, str]:
	"""The localization for a request, and its path without the locale prefix. Only a whole first
	segment is a prefix. Without one, `country` (`_country`) picks the market and `lang` the language."""
	markets = StorefrontMarkets.load(include_unpublished)
	prefix, path = split_locale_prefix(markets, path)

	if prefix:
		market, language, country = prefix.market, prefix.language, prefix.country
		root_prefix = get_prefix_path(prefix)
	else:
		country = normalize_country(country)
		market = markets.for_country(country)
		language = find_market_language(markets, market, lang)
		root_prefix = markets.prefix(market, language, country)

	languages = markets.languages
	localization = Localization(
		language=language,
		default_language=languages.default,
		available_languages=tuple(lang for lang in market.languages if languages.find(lang.code)),
		root_prefix=root_prefix,
		prefix_codes=markets.prefix_codes,
		market=market,
		available_markets=tuple((StorefrontMarkets.load() if include_unpublished else markets).all),
		country=country,
	)
	return localization, path


def strip_language_prefix(path: str, include_unpublished: bool = False) -> tuple[Language | None, str]:
	"""The language named by the first path segment, and the path without it.
	A market prefix names a language too."""
	prefix, rest = strip_locale_prefix(path, include_unpublished)
	return (prefix.language if prefix else None), rest


def strip_locale_prefix(path: str, include_unpublished: bool = False) -> tuple[LocalePrefix | None, str]:
	"""The market and language named by the first path segment, and the path without it."""
	return split_locale_prefix(StorefrontMarkets.load(include_unpublished), path)


@dataclass(frozen=True)
class LocalizedRequest:
	"""A storefront page request. Its URL alone decides the language, never `_lang`."""

	path: str
	route_path: str
	localization: Localization
	canonical_prefix: str
	redirect_to: str | None


def get_localization() -> Localization:
	"""The localization of the current request, or the one pinned by pin_localization()."""
	if pinned := get_pinned_localization():
		return pinned
	if localized := get_localized_request():
		return localized.localization
	return resolve_current_request()[0]


@contextmanager
def pin_localization(localization: Localization) -> Iterator[Localization]:
	"""Make get_localization() return `localization` inside the block.
	An editor preview renders its language this way, whatever the request path or `_lang` says."""
	previous = get_pinned_localization()
	frappe.local.commera_pinned_localization = localization
	try:
		yield localization
	finally:
		frappe.local.commera_pinned_localization = previous


def get_pinned_localization() -> Localization | None:
	return getattr(frappe.local, "commera_pinned_localization", None)


def get_route_path() -> str:
	"""The current request path without its language prefix.
	A request that localize_request left alone keeps its path, prefix and all."""
	if localized := get_localized_request():
		return localized.route_path
	request = getattr(frappe.local, "request", None)
	return request.path if request else "/"


def get_request_path() -> str:
	"""The path the browser asked for, with its language prefix."""
	if localized := get_localized_request():
		return localized.path
	request = getattr(frappe.local, "request", None)
	return request.path if request else ""


def get_localized_request() -> LocalizedRequest | None:
	"""Set by the before_request hook on storefront pages, which also strips the prefix off request.path."""
	return getattr(getattr(frappe.local, "request", None), "commera_localized", None)


def find_request_language(code: str | None) -> Language | None:
	"""`code` when the current user may open it: a published language, or any configured one for admins."""
	return StorefrontLanguages.load().find(code, is_commera_admin())


def resolve_current_request() -> tuple[Localization, str]:
	request = getattr(frappe.local, "request", None)
	form = frappe.form_dict
	path = request.path if request else "/"
	# A request may send any JSON type. request_cache also needs hashable arguments.
	lang = form.get("_lang")
	lang = lang if isinstance(lang, str) else None
	return resolve_cached(path, lang, is_commera_admin(), normalize_country(form.get("_country")))


@request_cache
def resolve_cached(
	path: str, lang: str | None, include_unpublished: bool, country: str | None
) -> tuple[Localization, str]:
	return resolve(path, lang, include_unpublished, country)


def find_market_language(markets: StorefrontMarkets, market: Market, code: str | None) -> Language:
	"""`code` when the market has it, else the market's default language."""
	if market.is_primary:
		return markets.languages.find(code, markets.include_hidden) or market.default_language
	return market.find_language(code) or market.default_language


def get_prefix_path(prefix: LocalePrefix) -> str:
	"""The path segment of `prefix`, in lowercase: `/AR/` redirects to `/ar/`."""
	language = prefix.language.code.lower()
	return f"/{language}-{prefix.country}" if prefix.country else f"/{language}"


def split_locale_prefix(markets: StorefrontMarkets, path: str) -> tuple[LocalePrefix | None, str]:
	segment, rest = split_first_segment(path)
	if match := markets.match_prefix(segment):
		return LocalePrefix(*match), rest
	if language := markets.languages.find(segment, markets.include_hidden):
		return LocalePrefix(markets.primary, language), rest
	return None, path


def split_first_segment(path: str) -> tuple[str, str]:
	segment, _slash, rest = (path or "/").lstrip("/").partition("/")
	return segment, f"/{rest}"
