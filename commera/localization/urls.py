import re
from collections.abc import Mapping
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import frappe
from frappe.utils import get_url

from commera.localization.languages import StorefrontLanguages
from commera.localization.markets import Market, StorefrontMarkets, market_hreflang
from commera.localization.resolver import (
	Localization,
	find_market_language,
	get_localization,
	get_request_path,
	strip_language_prefix,
)
from commera.localization.routing import clean_path, is_page_path, is_same_site, strip_legacy_prefix
from commera.roles import is_commera_admin

# Browsers drop tabs and newlines anywhere in a URL, and C0 controls and spaces before it.
IGNORED_URL_CHARACTERS = re.compile(r"[\t\n\r]")
LEADING_IGNORED_CHARACTERS = "".join(chr(code) for code in range(0x21))
SCRIPT_SCHEMES = ("javascript", "data", "vbscript")
# A script link becomes this: a link that goes nowhere.
INERT_LINK = "#"


def url(path: str | None) -> str | None:
	"""`path` in the current language and market: the default language has no prefix.
	A path that names a language moves to the current one. Use switch_url() to link another."""
	link = Link(path)
	if not link.is_page:
		return link.unchanged
	return link.localize(get_current_prefix(get_localization()))


def switch_url(
	path: str | None = None,
	query: str | Mapping | None = None,
	language: str | None = None,
	market: str | None = None,
	country: str | None = None,
) -> str:
	"""`path` in `language` and `market` (a handle; a `country` picks its market), with `query` merged in.
	Defaults to the current ones. What the shopper may not open falls back to the defaults."""
	link = Link(get_current_url() if path is None else path)
	if not link.is_page:
		return link.unchanged
	localization = get_localization()
	markets = StorefrontMarkets.load(is_commera_admin())
	target = pick_market(markets, localization, market, country)
	target_language = find_market_language(markets, target, language or localization.language.code)
	prefix = markets.prefix(target, target_language, country or localization.country)
	return link.localize(prefix, query or "")


def alternates(path: str | None = None) -> list[dict]:
	"""One absolute URL per published language and per enabled market's language and country,
	for hreflang and the sitemap. Empty for a store with one language and one market."""
	prefixes = get_locale_prefixes()
	link = Link(get_current_path() if path is None else path)
	if len(prefixes) < 2 or not link.is_page:
		return []
	return [
		{"lang": hreflang, "href": get_url(link.localize(prefix)), "x_default": x_default}
		for hreflang, prefix, x_default in prefixes
	]


def get_locale_prefixes() -> list[tuple[str, str, bool]]:
	"""(hreflang, prefix, x_default) of every URL root a shopper can open, the default first.
	x-default is the store default at the root. Market languages have no region: tags stay unique."""
	markets = StorefrontMarkets.load()
	languages = markets.languages
	prefixes = [
		(language.code, languages.prefix(language), language == languages.default)
		for language in languages.published
	]
	for _market, language, country, prefix in markets.market_prefixes():
		prefixes.append((market_hreflang(language, country), prefix, False))
	return prefixes


def get_current_prefix(localization: Localization) -> str:
	if localization.market and not localization.market.is_primary:
		return localization.root_prefix
	return StorefrontLanguages.load().prefix(localization.language)


def pick_market(
	markets: StorefrontMarkets, localization: Localization, handle: str | None, country: str | None
) -> Market:
	if country:
		return markets.for_country(country)
	if handle:
		return markets.find(handle) or markets.primary
	current = localization.market
	return (current and markets.find(current.handle)) or markets.primary


class Link:
	"""A link as a browser reads it. Only a same-site page path gets a locale prefix.
	Links off-site, relative links and /files/, /api/ and the like stay as they are."""

	def __init__(self, href: str | None):
		self.href = href
		self.read = IGNORED_URL_CHARACTERS.sub("", href or "").lstrip(LEADING_IGNORED_CHARACTERS)
		self.parts = urlsplit(self.read)

	@property
	def is_page(self) -> bool:
		return is_same_site(self.read) and is_page_path(self.parts.path)

	@property
	def unchanged(self) -> str | None:
		return INERT_LINK if self.parts.scheme in SCRIPT_SCHEMES else self.href

	def localize(self, prefix: str, query: str | Mapping | None = None) -> str:
		"""This page under `prefix`. A `query` is merged in and the result re-encoded."""
		route = clean_path(strip_prefix(self.parts.path))
		path = prefix + route if route != "/" else prefix or "/"
		query = self.parts.query if query is None else merge_query(self.parts.query, query)
		return urlunsplit(("", "", path, query, self.parts.fragment))


def strip_prefix(path: str) -> str:
	language, rest = strip_language_prefix(path, include_unpublished=True)
	return rest if language else strip_legacy_prefix(path)


def merge_query(current: str, query: str | Mapping) -> str:
	"""`current` with `query` on top. A key in `query` replaces all its values; None drops it."""
	if isinstance(query, Mapping):
		keys = set(query)
		pairs = [
			(key, item)
			for key, value in query.items()
			if value is not None
			for item in (value if isinstance(value, list | tuple) else [value])
		]
	else:
		pairs = parse_qsl(query.lstrip("?"), keep_blank_values=True)
		keys = {key for key, _value in pairs}
	kept = [(key, value) for key, value in parse_qsl(current, keep_blank_values=True) if key not in keys]
	return urlencode(kept + pairs)


def get_current_url() -> str:
	return urlunsplit(("", "", get_current_path(), get_current_query(), ""))


def get_current_path() -> str:
	# The request path arrives percent-decoded.
	return quote(clean_path(get_request_path() or "/"), safe="/:,;=@!$&'()*+~")


def get_current_query() -> str:
	request = getattr(frappe.local, "request", None)
	return frappe.safe_decode(request.query_string) if request else ""
