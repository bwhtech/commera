from dataclasses import dataclass

import frappe
from frappe.utils.caching import request_cache

from commera.localization.languages import Language, StorefrontLanguages
from commera.roles import is_commera_admin


@dataclass(frozen=True)
class Localization:
	language: Language
	default_language: Language
	available_languages: tuple[Language, ...]
	root_prefix: str

	def as_dict(self) -> dict:
		return {
			"language": self.language.as_dict(),
			"default_language": self.default_language.as_dict(),
			"available_languages": [language.as_dict() for language in self.available_languages],
			"root_prefix": self.root_prefix,
		}


def resolve(
	path: str, lang: str | None = None, include_unpublished: bool = False
) -> tuple[Localization, str]:
	"""The localization for a request, and its path without the language prefix.
	Only a whole first segment is a prefix. Without one, `lang` (`_lang`) wins, then the default."""
	languages = StorefrontLanguages.load()
	prefix_language, path = split_language_prefix(languages, path, include_unpublished)

	if language := prefix_language:
		root_prefix = f"/{language.code.lower()}"
	else:
		language = languages.find(lang, include_unpublished) or languages.default
		root_prefix = languages.prefix(language)

	localization = Localization(
		language=language,
		default_language=languages.default,
		available_languages=tuple(languages.published),
		root_prefix=root_prefix,
	)
	return localization, path


def strip_language_prefix(path: str, include_unpublished: bool = False) -> tuple[Language | None, str]:
	"""The language named by the first path segment, and the path without it."""
	return split_language_prefix(StorefrontLanguages.load(), path, include_unpublished)


@dataclass(frozen=True)
class LocalizedRequest:
	"""A storefront page request. Its URL alone decides the language, never `_lang`."""

	path: str
	route_path: str
	localization: Localization
	canonical_prefix: str
	redirect_to: str | None


def get_localization() -> Localization:
	"""The localization of the current request."""
	if localized := get_localized_request():
		return localized.localization
	return resolve_current_request()[0]


def get_route_path() -> str:
	"""The current request path without its language prefix."""
	if localized := get_localized_request():
		return localized.route_path
	return resolve_current_request()[1]


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
	return resolve_cached(request.path if request else "/", frappe.form_dict.get("_lang"), is_commera_admin())


@request_cache
def resolve_cached(path: str, lang: str | None, include_unpublished: bool) -> tuple[Localization, str]:
	return resolve(path, lang, include_unpublished)


def split_language_prefix(languages, path, include_unpublished) -> tuple[Language | None, str]:
	segment, rest = split_first_segment(path)
	if language := languages.find(segment, include_unpublished):
		return language, rest
	return None, path


def split_first_segment(path: str) -> tuple[str, str]:
	segment, _slash, rest = (path or "/").lstrip("/").partition("/")
	return segment, f"/{rest}"
