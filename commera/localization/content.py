"""Translated record content, such as product titles, read from Content Translation rows.
These rows stay out of Frappe's Translation dictionary, so the per-request and browser dictionaries stay small."""

from dataclasses import dataclass

import frappe
from frappe import _
from frappe.model.base_document import get_controller
from frappe.utils import create_batch, cstr
from frappe.utils.data import sha256_hash

from commera.localization.resolver import Localization, get_localization
from commera.localization.resources import get_translatable_fields

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
	doctype = doctype or records[0].get("doctype")
	sources = get_sources(doctype, records, fields)
	if language == localization.default_language.code:
		return [{field: TranslatedValue(source[field], CURRENT) for field in fields} for source in sources]

	translations = fetch_translations(doctype, [record.get("name") for record in records], fields, language)
	return [
		{
			field: resolve_value(source[field], translations.get((record.get("name"), field)), language)
			for field in fields
		}
		for record, source in zip(records, sources, strict=True)
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
	"""doc_events on_trash: drop the translations of a deleted record and of its child rows."""
	frappe.db.delete(DOCTYPE, {"reference_doctype": doc.doctype, "reference_name": doc.name})
	rows = {}
	for row in doc.get_all_children():
		rows.setdefault(row.doctype, []).append(row.name)
	for doctype, names in rows.items():
		if get_translatable_fields(doctype):
			frappe.db.delete(DOCTYPE, {"reference_doctype": doctype, "reference_name": ("in", names)})


def delete_removed_row_translations(doc, method=None):
	"""doc_events on_update: drop the translations of translatable child rows the save removed."""
	before = doc.get_doc_before_save()
	if not before:
		return
	for table in doc.meta.get_table_fields():
		if not get_translatable_fields(table.options):
			continue
		kept = {row.name for row in doc.get(table.fieldname)}
		removed = [row.name for row in before.get(table.fieldname) if row.name not in kept]
		if removed:
			frappe.db.delete(DOCTYPE, {"reference_doctype": table.options, "reference_name": ("in", removed)})


def move_translations(doctype: str, old_name: str, new_name: str):
	"""Point a record's translations at its copy, as when a child row moves to another parent."""
	frappe.db.set_value(
		DOCTYPE, {"reference_doctype": doctype, "reference_name": old_name}, "reference_name", new_name
	)


def read_source(doctype: str, name: str, field: str):
	"""The text a translation of the field translates, read as `translate()` reads it."""
	if frappe.get_meta(doctype).has_field(field):
		return frappe.db.get_value(doctype, name, field)
	return read_derived_sources(doctype, field, [name]).get(name)


def get_sources(doctype: str | None, records: list, fields: list[str]) -> list[dict[str, str]]:
	"""Each record's source of `fields`. A field without a column that the record lacks is read
	for all records at once, through the controller's `get_translation_sources`."""
	sources = [{field: record.get(field) for field in fields} for record in records]
	for field in get_derived_fields(doctype, fields):
		missing = [
			(record.get("name"), source)
			for record, source in zip(records, sources, strict=True)
			if source[field] is None
		]
		derived = read_derived_sources(doctype, field, [name for name, _source in missing])
		for name, source in missing:
			source[field] = derived.get(name)
	return [{field: cstr(value) for field, value in source.items()} for source in sources]


def get_derived_fields(doctype: str | None, fields: list[str]) -> list[str]:
	if not doctype:
		return []
	meta = frappe.get_meta(doctype)
	return [field for field in fields if not meta.has_field(field)]


def read_derived_sources(doctype: str, field: str, names: list) -> dict:
	"""{name: source} from the controller's `get_translation_sources(field, names)`, one query per batch."""
	get_translation_sources = getattr(get_controller(doctype), "get_translation_sources", None)
	sources = {}
	if not get_translation_sources:
		return sources
	for batch in create_batch([name for name in names if name], BATCH_SIZE):
		sources.update(get_translation_sources(field, batch))
	return sources


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
		return TranslatedValue(value, get_status(source, value, source_hash))
	return TranslatedValue(_(source, lang=language) if source else source, MISSING)


def get_status(source, value: str | None, source_hash: str | None) -> str:
	"""Missing without a translation; outdated when the source changed after it was written."""
	if not value:
		return MISSING
	return CURRENT if source_hash == get_source_hash(source) else OUTDATED


def count_column_statuses(doctype: str, field: str, language: str) -> dict[str, int]:
	"""{status: count} of a column field's shop-wide translations, aggregated in SQL. MariaDB's
	SHA2 matches get_source_hash for text, so status is decided without reading a source."""
	rows = frappe.db.sql(
		f"""
		select
			case
				when ifnull(translation.translated_value, '') = '' then %(missing)s
				when translation.source_hash = sha2(record.`{field}`, 256) then %(current)s
				else %(outdated)s
			end as status,
			count(*)
		from `tab{doctype}` record
		left join `tab{DOCTYPE}` translation
			on translation.reference_doctype = %(doctype)s
			and translation.reference_name = record.name
			and translation.reference_field = %(field)s
			and translation.language = %(language)s
			and ifnull(translation.market, '') = ''
		where ifnull(record.`{field}`, '') != ''
		group by status""",
		{
			"doctype": doctype,
			"field": field,
			"language": language,
			"missing": MISSING,
			"outdated": OUTDATED,
			"current": CURRENT,
		},
	)
	return dict(rows)
