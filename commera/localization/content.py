"""Translated record content, such as product titles, read from Content Translation rows.
These rows stay out of Frappe's Translation dictionary, so the per-request and browser dictionaries stay small."""

import html
import re
from dataclasses import dataclass

import frappe
from frappe import _
from frappe.model.base_document import get_controller
from frappe.query_builder import Case, CustomFunction, DocType
from frappe.query_builder.functions import Count, IfNull
from frappe.utils import create_batch, cstr
from frappe.utils.data import sha256_hash

from commera.localization.markets import MARKET_DOCTYPE, PRIMARY_MARKET, Market
from commera.localization.resolver import Localization, get_localization

Sha2 = CustomFunction("SHA2", ["value", "length"])
DOCTYPE = "Content Translation"
MISSING, OUTDATED, CURRENT = "missing", "outdated", "current"
SHOP_WIDE = ""
BATCH_SIZE = 500
# The stored copy of a source, shown when it changes, is cut to this many characters.
SOURCE_TEXT_LENGTH = 500
FILE_FIELDTYPES = ("Attach", "Attach Image")
HTML_TAG = re.compile(r"<[a-z][^>]*>", re.IGNORECASE)
ANY_TAG = re.compile(r"</?[a-z][^>]*>", re.IGNORECASE)


@dataclass(frozen=True)
class TranslatedValue:
	value: str
	# missing: no translation; outdated: the source changed after it was written.
	status: str


def translate(
	records: list, fields: list[str], localization: Localization | None = None, doctype: str | None = None
) -> list[dict[str, TranslatedValue]]:
	"""Each record's `fields` in the localization's language, in record order. `doctype` names rows that
	lack one. Lookup: the market's translation, the shop-wide one (not in the default language), `_()`."""
	localization = localization or get_localization()
	language = localization.language.code
	if not records:
		return []
	doctype = doctype or records[0].get("doctype")
	sources = get_sources(doctype, records, fields)
	market = get_lookup_market(localization.market)
	# The default language is the source: only a market may override it.
	is_default = language == localization.default_language.code
	if is_default and market == SHOP_WIDE:
		return [{field: TranslatedValue(source[field], CURRENT) for field in fields} for source in sources]

	names = [record.get("name") for record in records]
	translations = fetch_translations(doctype, names, fields, language, market, shop_wide=not is_default)
	resolve = resolve_source if is_default else resolve_value
	return [
		{
			field: resolve(source[field], translations.get((record.get("name"), field)), language)
			for field in fields
		}
		for record, source in zip(records, sources, strict=True)
	]


def register(
	doctype: str, name: str, field: str, language: str, value: str, market: str | None = None
) -> str:
	"""Write a translation of a record's field, shop-wide or for `market`, marked current against the
	field's source now. Returns the Content Translation name."""
	key = {
		"reference_doctype": doctype,
		"reference_name": name,
		"reference_field": field,
		"language": language,
		"market": get_market_key(market),
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


def get_market_key(market: str | None) -> str:
	"""The stored market of a translation: shop-wide for none or the primary market. Throws for a
	market that does not exist; a disabled one is fine, as it is prepared before launch."""
	key = find_market_key(market)
	if key is None:
		frappe.throw(_("Market {0} does not exist.").format(frappe.bold(market)), frappe.DoesNotExistError)
	return key


def find_market_key(market: str | None) -> str | None:
	"""Like `get_market_key`, but None for a market that does not exist. Any case matches."""
	market = cstr(market).strip()
	if not market or market.lower() == PRIMARY_MARKET:
		return SHOP_WIDE
	if not frappe.db.table_exists(MARKET_DOCTYPE):
		return None
	return frappe.db.get_value(MARKET_DOCTYPE, market, "name")


def get_lookup_market(market: Market | None) -> str:
	return SHOP_WIDE if market is None or market.is_primary else market.handle


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
		if has_translatable_fields(doctype):
			frappe.db.delete(DOCTYPE, {"reference_doctype": doctype, "reference_name": ("in", names)})


def delete_removed_row_translations(doc, method=None):
	"""doc_events on_update: drop the translations of translatable child rows the save removed."""
	before = doc.get_doc_before_save()
	if not before:
		return
	for table in doc.meta.get_table_fields():
		if not has_translatable_fields(table.options):
			continue
		kept = {row.name for row in doc.get(table.fieldname)}
		removed = [row.name for row in before.get(table.fieldname) if row.name not in kept]
		if removed:
			frappe.db.delete(DOCTYPE, {"reference_doctype": table.options, "reference_name": ("in", removed)})


def rename_translations(doc, method=None, old=None, new=None, merge=False):
	"""Move translations in the rename transaction. A merge keeps the target's duplicate keys."""
	if merge:
		drop_merged_duplicates(doc.doctype, old, new)
	move_translations(doc.doctype, old, new)


def drop_merged_duplicates(doctype: str, old: str, new: str):
	translation, target = DocType(DOCTYPE), DocType(DOCTYPE).as_("target")
	duplicates = (
		frappe.qb.from_(translation)
		.join(target)
		.on(
			(target.reference_doctype == translation.reference_doctype)
			& (target.reference_field == translation.reference_field)
			& (target.language == translation.language)
			& (target.market == translation.market)
		)
		.select(translation.name)
		.where(
			(translation.reference_doctype == doctype)
			& (translation.reference_name == old)
			& (target.reference_name == new)
		)
		.run(pluck=True)
	)
	if duplicates:
		frappe.db.delete(DOCTYPE, {"name": ("in", duplicates)})


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


def get_source_text(doctype: str, field: str, source) -> str | None:
	"""The source as short plain text, kept with a translation to show what it was written against.
	None for a file field, whose source is a file path."""
	meta = frappe.get_meta(doctype)
	if meta.has_field(field) and meta.get_field(field).fieldtype in FILE_FIELDTYPES:
		return None
	text = cstr(source)
	if HTML_TAG.search(text):
		# A space for each tag, so paragraphs do not run together.
		text = html.unescape(ANY_TAG.sub(" ", text))
	text = " ".join(text.split())
	if len(text) > SOURCE_TEXT_LENGTH:
		text = text[: SOURCE_TEXT_LENGTH - 1] + "…"
	return text or None


def fetch_translations(
	doctype: str,
	names: list,
	fields: list[str],
	language: str,
	market: str = SHOP_WIDE,
	shop_wide: bool = True,
) -> dict:
	"""{(name, field): (translated value, source hash)}, in one query per batch. A non-empty translation
	for `market` wins over the shop-wide one, and its hash decides the status."""
	markets = list({SHOP_WIDE, market} if shop_wide else {market})
	translations = {}
	for batch in create_batch(list({cstr(name) for name in names if name}), BATCH_SIZE):
		rows = frappe.get_all(
			DOCTYPE,
			filters={
				"reference_doctype": doctype,
				"reference_name": ("in", batch),
				"reference_field": ("in", fields),
				"language": language,
				"market": ("in", markets),
				"translated_value": ("is", "set"),
			},
			fields=["reference_name", "reference_field", "market", "translated_value", "source_hash"],
		)
		for row in rows:
			key = (row.reference_name, row.reference_field)
			if row.market == market or key not in translations:
				translations[key] = (row.translated_value, row.source_hash)
	return translations


def resolve_value(source: str, translation: tuple | None, language: str) -> TranslatedValue:
	if translation and translation[0]:
		return resolve_translation(source, translation)
	return TranslatedValue(_(source, lang=language) if source else source, MISSING)


def resolve_source(source: str, translation: tuple | None, language: str) -> TranslatedValue:
	"""A market's override of the source, in the default language, else the source itself."""
	if translation and translation[0]:
		return resolve_translation(source, translation)
	return TranslatedValue(source, CURRENT)


def resolve_translation(source: str, translation: tuple) -> TranslatedValue:
	value, source_hash = translation
	return TranslatedValue(value, get_status(source, value, source_hash))


def get_status(source, value: str | None, source_hash: str | None) -> str:
	"""Missing without a translation; outdated when the source changed after it was written, or is gone."""
	if not value:
		return MISSING
	return CURRENT if source and source_hash == get_source_hash(source) else OUTDATED


def count_column_statuses(doctype: str, field: str, language: str) -> dict[str, int]:
	"""{status: count} of a column field's shop-wide translations, aggregated in SQL. MariaDB's
	SHA2 matches get_source_hash for text, so status is decided without reading a source."""
	record, translation = DocType(doctype), DocType(DOCTYPE)
	status = (
		Case()
		.when(IfNull(translation.translated_value, "") == "", MISSING)
		.when(translation.source_hash == Sha2(record[field], 256), CURRENT)
		.else_(OUTDATED)
	)
	query = (
		frappe.qb.from_(record)
		.left_join(translation)
		.on(
			(translation.reference_doctype == doctype)
			& (translation.reference_name == record.name)
			& (translation.reference_field == field)
			& (translation.language == language)
			& (IfNull(translation.market, "") == "")
		)
		.where(IfNull(record[field], "") != "")
		.select(status, Count("*"))
		.groupby(status)
	)
	return dict(query.run())


def has_translatable_fields(doctype: str) -> bool:
	# Imported here: resources imports this module.
	from commera.localization.resources import get_translatable_fields

	return bool(get_translatable_fields(doctype))
