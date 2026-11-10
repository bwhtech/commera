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
	segment, rest = split_first_segment(path)

	if language := languages.find(segment, include_unpublished):
		root_prefix, path = f"/{language.code.lower()}", rest
	else:
		language = languages.find(lang, include_unpublished) or languages.default
		root_prefix = "" if language == languages.default else f"/{language.code.lower()}"

	localization = Localization(
		language=language,
		default_language=languages.default,
		available_languages=tuple(languages.published),
		root_prefix=root_prefix,
	)
	return localization, path


def get_localization() -> Localization:
	"""The localization of the current request."""
	return resolve_current_request()[0]


def find_request_language(code: str | None) -> Language | None:
	"""`code` when the current user may open it: a published language, or any configured one for admins."""
	return StorefrontLanguages.load().find(code, is_commera_admin())


def apply_request_language():
	"""Set frappe.local.lang when the path starts with a storefront language prefix."""
	localization, path = resolve_current_request()
	if path != frappe.request.path:
		frappe.local.lang = localization.language.code


def resolve_current_request() -> tuple[Localization, str]:
	request = getattr(frappe.local, "request", None)
	return resolve_cached(request.path if request else "/", frappe.form_dict.get("_lang"), is_commera_admin())


@request_cache
def resolve_cached(path: str, lang: str | None, include_unpublished: bool) -> tuple[Localization, str]:
	return resolve(path, lang, include_unpublished)


def split_first_segment(path: str) -> tuple[str, str]:
	segment, _slash, rest = (path or "/").lstrip("/").partition("/")
	return segment, f"/{rest}"
