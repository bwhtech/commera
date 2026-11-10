from dataclasses import asdict, dataclass
from functools import lru_cache

import frappe
from babel import Locale, UnknownLocaleError
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
	try:
		locale = Locale.parse(code, sep="-")
	except (UnknownLocaleError, ValueError):
		name = frappe.db.get_value("Language", code, "language_name") or code
		return name, name
	return locale.get_display_name("en"), locale.get_display_name(locale)
