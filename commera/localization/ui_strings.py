"""The storefront's client dictionary: Frappe's UI strings with the merchant's Translation overrides.
Record content stays out: it lives in Content Translation and comes translated from the server."""

import frappe
from frappe import _
from frappe.translate import get_all_translations, get_translation_version, get_user_translations

from commera.localization.languages import StorefrontLanguages
from commera.roles import is_commera_admin

# Frappe's source strings are English: an English page needs a dictionary only for overrides.
SOURCE_LANGUAGE = "en"


def get_ui_strings(lang: str) -> dict[str, str]:
	"""The dictionary of a published language. Admins may preview an unpublished one."""
	language = StorefrontLanguages.load().find(lang, include_unpublished=is_commera_admin())
	if not language:
		frappe.throw(_("Language {0} is not available").format(lang), frappe.DoesNotExistError)
	return get_all_translations(language.code)


def get_ui_strings_version(language: str) -> str | None:
	"""The version a page puts in its dictionary URL, or None when the page needs no dictionary."""
	if language == SOURCE_LANGUAGE and not get_user_translations(SOURCE_LANGUAGE):
		return None
	return get_translation_version()
