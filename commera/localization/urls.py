from collections.abc import Mapping
from urllib.parse import quote, urlencode, urlsplit

import frappe
from frappe.utils import get_url

from commera.localization.languages import StorefrontLanguages
from commera.localization.resolver import get_localization, get_request_path, strip_language_prefix
from commera.localization.routing import is_page_path, strip_legacy_prefix
from commera.roles import is_commera_admin


def url(path: str | None) -> str | None:
	"""`path` in the current language: the default language has no prefix.
	A path that names a language moves to the current one. Use switch_url() to link another."""
	if not is_storefront_link(path):
		return path
	return localize(StorefrontLanguages.load().prefix(get_localization().language), path)


def switch_url(
	path: str | None = None, query: str | Mapping | None = None, language: str | None = None
) -> str:
	"""`path` in `language`, with `query`. Defaults to the current page, its query and its language.
	A language the shopper may not open gives the default language."""
	if path is None:
		path = get_current_path()
		query = get_current_query() if query is None else query
	languages = StorefrontLanguages.load()
	if language:
		target = languages.find(language, is_commera_admin()) or languages.default
	else:
		target = get_localization().language
	target_url = localize(languages.prefix(target), path)
	query = format_query(query)
	return f"{target_url}?{query}" if query else target_url


def alternates(path: str | None = None) -> list[dict]:
	"""One absolute URL per published language, default first, for hreflang and the sitemap.
	Empty for a single-language store: it has no other version to point search engines to."""
	languages = StorefrontLanguages.load()
	if len(languages.published) < 2:
		return []
	path = get_current_path() if path is None else path
	return [
		{
			"lang": language.code,
			"href": get_url(localize(languages.prefix(language), path)),
			"x_default": language == languages.default,
		}
		for language in languages.published
	]


def localize(prefix: str, path: str) -> str:
	parts = urlsplit(path)
	route = strip_prefix(parts.path or "/")
	localized = prefix + route if route != "/" else prefix or "/"
	return parts._replace(path=localized).geturl()


def strip_prefix(path: str) -> str:
	language, rest = strip_language_prefix(path, include_unpublished=True)
	return rest if language else strip_legacy_prefix(path)


def is_storefront_link(path: str | None) -> bool:
	"""A same-site page path. Links off-site, relative links and /files/, /api/ and the like stay as they are."""
	if not path or not path.startswith("/") or path.startswith(("//", "/\\")):
		return False
	return is_page_path(urlsplit(path).path)


def get_current_path() -> str:
	# The request path arrives percent-decoded.
	return quote(get_request_path() or "/", safe="/:,;=@!$&'()*+~")


def get_current_query() -> str:
	request = getattr(frappe.local, "request", None)
	return frappe.safe_decode(request.query_string) if request else ""


def format_query(query: str | Mapping | None) -> str:
	if isinstance(query, Mapping):
		return urlencode({key: value for key, value in query.items() if value is not None}, doseq=True)
	return (query or "").lstrip("?")
