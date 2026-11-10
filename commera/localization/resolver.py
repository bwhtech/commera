from dataclasses import dataclass

import frappe
from frappe.utils.caching import request_cache

from commera.localization.languages import Language, StorefrontLanguages
from commera.roles import is_commera_admin

# Desk, API, assets and Frappe's own pages keep Frappe's language: the user's, not the storefront's.
SYSTEM_SEGMENTS = frozenset(
	{
		"api",
		"app",
		"desk",
		"assets",
		"files",
		"private",
		"commera",
		"socket.io",
		"print",
		"printview",
		"login",
		"logout",
		"update-password",
	}
)


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
		root_prefix, path = f"/{segment}", rest
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


@request_cache
def get_localization() -> Localization:
	"""The localization of the current request."""
	request = getattr(frappe.local, "request", None)
	path = request.path if request else "/"
	localization, _path = resolve(path, frappe.form_dict.get("_lang"), is_commera_admin())
	return localization


def apply_request_language():
	"""Set frappe.local.lang from the storefront URL, except on desk, API and system paths."""
	segment, _rest = split_first_segment(frappe.request.path)
	if segment in SYSTEM_SEGMENTS:
		return
	frappe.local.lang = get_localization().language.code


def split_first_segment(path: str) -> tuple[str, str]:
	segment, _slash, rest = (path or "/").lstrip("/").partition("/")
	return segment, f"/{rest}"
