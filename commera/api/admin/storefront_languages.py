# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""The dashboard's Languages settings: the storefront languages, their order and the default one.
Every write answers with the whole screen, so the panel adopts the server's truth."""

import frappe
from frappe import _
from frappe.utils import cint

from commera.localization.languages import (
	MAX_STOREFRONT_LANGUAGES,
	Language,
	get_default_language_code,
)
from commera.roles import is_commera_admin

SETTINGS_DOCTYPE = "Commera Settings"


# Not GET-only: the dashboard reads it through createAdminCaller, which POSTs.
@frappe.whitelist()
def get_storefront_languages() -> dict:
	require_store_admin()
	return LanguageSettings(frappe.get_cached_doc(SETTINGS_DOCTYPE)).as_dict()


@frappe.whitelist(methods=["POST"])
def add_storefront_language(language: str, published: bool | int = 0) -> dict:
	settings = LanguageSettings.for_update()
	settings.add(language, cint(published))
	return settings.save()


@frappe.whitelist(methods=["POST"])
def remove_storefront_language(language: str) -> dict:
	settings = LanguageSettings.for_update()
	settings.remove(language)
	return settings.save()


@frappe.whitelist(methods=["POST"])
def set_storefront_language_published(language: str, published: bool | int) -> dict:
	settings = LanguageSettings.for_update()
	settings.set_published(language, cint(published))
	return settings.save()


@frappe.whitelist(methods=["POST"])
def move_storefront_language(language: str, offset: int) -> dict:
	settings = LanguageSettings.for_update()
	settings.move(language, cint(offset))
	return settings.save()


@frappe.whitelist(methods=["POST"])
def set_default_storefront_language(language: str) -> dict:
	settings = LanguageSettings.for_update()
	settings.make_default(language)
	return settings.save()


class LanguageSettings:
	"""The language rows of Commera Settings, in their stored order. The doctype validates the rest:
	the limit, duplicates and a published default."""

	def __init__(self, doc):
		self.doc = doc
		self.default = get_default_language_code(doc)

	@classmethod
	def for_update(cls) -> "LanguageSettings":
		require_store_admin()
		settings = cls(frappe.get_doc(SETTINGS_DOCTYPE))
		settings.ensure_default_row()
		return settings

	@property
	def rows(self) -> list:
		return self.doc.get("storefront_languages") or []

	def as_dict(self) -> dict:
		rows = [(row.language, bool(row.published)) for row in self.rows]
		if not self.find(self.default):
			rows.insert(0, (self.default, True))
		return {
			"default_language": self.default,
			"max_languages": MAX_STOREFRONT_LANGUAGES,
			"languages": [
				{**Language.from_code(code).as_dict(), "published": published or code == self.default}
				for code, published in rows
			],
		}

	def save(self) -> dict:
		self.doc.save(ignore_permissions=True)
		return LanguageSettings(self.doc).as_dict()

	def add(self, code: str, published: int):
		if not frappe.db.exists("Language", {"name": code, "enabled": 1}):
			frappe.throw(_("{0} is not an enabled language.").format(code))
		if self.find(code):
			frappe.throw(_("{0} is already a storefront language.").format(name_of(code)))
		self.doc.append("storefront_languages", {"language": code, "published": published})

	def remove(self, code: str):
		if code == self.default:
			frappe.throw(_("Make another language the default before you remove {0}.").format(name_of(code)))
		self.doc.remove(self.get_row(code))
		self.renumber()

	def set_published(self, code: str, published: int):
		if code == self.default and not published:
			frappe.throw(_("Shoppers always see the default language."))
		self.get_row(code).published = published

	def move(self, code: str, offset: int):
		rows = self.rows
		row = self.get_row(code)
		index = rows.index(row)
		target = min(max(index + offset, 0), len(rows) - 1)
		rows.insert(target, rows.pop(index))
		self.renumber()

	def make_default(self, code: str):
		if not self.get_row(code).published:
			frappe.throw(_("Publish {0} before you make it the default language.").format(name_of(code)))
		self.doc.default_storefront_language = code
		self.default = code

	def ensure_default_row(self):
		"""A store set up before the language table may have a default without a row."""
		if not self.find(self.default):
			self.doc.append("storefront_languages", {"language": self.default, "published": 1})
			self.rows.insert(0, self.rows.pop())
			self.renumber()

	def find(self, code: str):
		return next((row for row in self.rows if row.language == code), None)

	def get_row(self, code: str):
		if row := self.find(code):
			return row
		frappe.throw(_("{0} is not a storefront language.").format(name_of(code)))

	def renumber(self):
		for idx, row in enumerate(self.rows, start=1):
			row.idx = idx


def name_of(code: str) -> str:
	return Language.from_code(code).name


def require_store_admin():
	if not is_commera_admin():
		frappe.throw(_("Only store administrators can manage storefront languages."), frappe.PermissionError)
