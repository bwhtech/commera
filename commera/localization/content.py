"""Translated record content, such as product titles, read from Content Translation rows.
These rows stay out of Frappe's Translation dictionary, so the per-request and browser dictionaries stay small."""

from dataclasses import dataclass

import frappe
from frappe import _
from frappe.utils import create_batch, cstr
from frappe.utils.data import sha256_hash

from commera.localization.resolver import Localization, get_localization

DOCTYPE = "Content Translation"
MISSING, OUTDATED, CURRENT = "missing", "outdated", "current"
SHOP_WIDE = ""
BATCH_SIZE = 500


@dataclass(frozen=True)
class TranslatedValue:
	value: str
	# missing: no translation; outdated: the source changed after it was written.
	status: str


def translate(
	records: list, fields: list[str], localization: Localization | None = None, doctype: str | None = None
) -> list[dict[str, TranslatedValue]]:
	"""Each record's `fields` in the localization's language, in the order of `records`.
	Without a translation: Frappe `_()` of the source, then the source. `doctype` names rows that lack one."""
	localization = localization or get_localization()
	language = localization.language.code
	if not records:
		return []
	if language == localization.default_language.code:
		return [
			{field: TranslatedValue(get_source(record, field), CURRENT) for field in fields}
			for record in records
		]

	doctype = doctype or records[0].get("doctype")
	translations = fetch_translations(doctype, [record.get("name") for record in records], fields, language)
	return [
		{
			field: resolve_value(
				get_source(record, field), translations.get((record.get("name"), field)), language
			)
			for field in fields
		}
		for record in records
	]


def register(
	doctype: str, name: str, field: str, language: str, value: str, market: str | None = None
) -> str:
	"""Write a translation of a record's field, marked current against the field's source now.
	Returns the Content Translation name."""
	key = {
		"reference_doctype": doctype,
		"reference_name": name,
		"reference_field": field,
		"language": language,
		"market": market or SHOP_WIDE,
	}
	if existing := frappe.db.get_value(DOCTYPE, key):
		return save_translation(frappe.get_doc(DOCTYPE, existing), value)

	frappe.db.savepoint("register_content_translation")
	try:
		return save_translation(frappe.new_doc(DOCTYPE).update(key), value)
	except (frappe.UniqueValidationError, frappe.DuplicateEntryError):
		# Another request inserted the same key first: update its row instead.
		frappe.db.rollback(save_point="register_content_translation")
		return save_translation(frappe.get_doc(DOCTYPE, frappe.db.get_value(DOCTYPE, key)), value)


def save_translation(translation, value: str) -> str:
	translation.translated_value = value
	translation.flags.refresh_source_hash = True
	translation.save()
	return translation.name


def delete_translations(doc, method=None):
	"""doc_events on_trash: drop the translations of a deleted record."""
	frappe.db.delete(DOCTYPE, {"reference_doctype": doc.doctype, "reference_name": doc.name})


def get_source_hash(source) -> str:
	return sha256_hash(cstr(source))


def fetch_translations(doctype: str, names: list, fields: list[str], language: str) -> dict:
	"""{(name, field): (translated value, source hash)} of shop-wide translations, in one query per batch."""
	translations = {}
	for batch in create_batch(list({cstr(name) for name in names if name}), BATCH_SIZE):
		rows = frappe.get_all(
			DOCTYPE,
			filters={
				"reference_doctype": doctype,
				"reference_name": ("in", batch),
				"reference_field": ("in", fields),
				"language": language,
				"market": SHOP_WIDE,
			},
			fields=["reference_name", "reference_field", "translated_value", "source_hash"],
		)
		for row in rows:
			translations[(row.reference_name, row.reference_field)] = (row.translated_value, row.source_hash)
	return translations


def resolve_value(source: str, translation: tuple | None, language: str) -> TranslatedValue:
	if translation and translation[0]:
		value, source_hash = translation
		return TranslatedValue(value, CURRENT if source_hash == get_source_hash(source) else OUTDATED)
	return TranslatedValue(_(source, lang=language) if source else source, MISSING)


def get_source(record, field: str) -> str:
	return cstr(record.get(field))
