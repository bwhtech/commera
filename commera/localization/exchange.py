"""Translation exchange: one language's translations as a CSV in Shopify's column shape, and an
import that writes such a file back through `register()`, one row at a time."""

import csv
import io
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field

import frappe
from frappe import _
from frappe.utils import create_batch, cstr
from frappe.utils.csvutils import escape_formula_injection, unescape_formula_injection

from commera.localization.content import (
	BATCH_SIZE,
	CURRENT,
	DOCTYPE,
	MISSING,
	OUTDATED,
	SHOP_WIDE,
	fetch_translations,
	get_source_hash,
	get_sources,
	register,
)
from commera.localization.languages import StorefrontLanguages
from commera.localization.resources import TranslatableResource, get_translatable_resources

COLUMNS = (
	"Type",
	"Identification",
	"Field",
	"Locale",
	"Market",
	"Status",
	"Default content",
	"Translated content",
)
IMPORT_COLUMNS = ("Type", "Identification", "Field", "Locale", "Market", "Translated content")
MAX_IMPORT_ROWS = 10_000
# Markets arrive with #450. Until that doctype exists, a row for a market is an error.
MARKET_DOCTYPE = "Commera Market"


@dataclass(frozen=True)
class Entry:
	"""One translatable field of one record, in one language."""

	type: str
	identification: str
	field: str
	status: str
	default: str
	translated: str

	def as_row(self, language: str) -> list[str]:
		return [
			self.type,
			self.identification,
			self.field,
			language,
			SHOP_WIDE,
			self.status,
			self.default,
			self.translated,
		]


@dataclass
class ImportReport:
	updated: int = 0
	unchanged: int = 0
	# Rows with no translated content: Shopify leaves those translations as they are.
	skipped: int = 0
	errors: list[dict] = field(default_factory=list)

	def as_dict(self) -> dict:
		return asdict(self)


class RowError(Exception):
	pass


def get_exchange_language(code: str) -> str:
	"""A configured storefront language other than the default, which has nothing to translate."""
	languages = StorefrontLanguages.load()
	language = languages.find(code, include_unpublished=True)
	if not language or language == languages.default:
		frappe.throw(_("{0} is not a storefront language you translate into.").format(cstr(code)))
	return language.code


def export_csv(language: str) -> str:
	"""Every field with a source or a translation. Formula-like cells get a leading quote (OWASP)."""
	language = get_exchange_language(language)
	buffer = io.StringIO()
	writer = csv.writer(buffer)
	writer.writerow(COLUMNS)
	for entry in iter_entries(language):
		if entry.default or entry.translated:
			writer.writerow([escape_formula_injection(cell) for cell in entry.as_row(language)])
	return buffer.getvalue()


def import_csv(content: bytes | str, language: str) -> ImportReport:
	return TranslationImport(read_rows(content), get_exchange_language(language)).run()


class TranslationImport:
	"""Matches each row on type, identification, field, locale and market, and writes the changed ones.
	A bad row becomes an error in the report and the next row is read."""

	def __init__(self, rows: list[tuple[int, dict]], language: str):
		self.rows = rows
		self.language = language
		self.report = ImportReport()
		self.resources = {resource.type: resource for resource in get_translatable_resources()}
		types = {row["Type"] for _number, row in rows} & set(self.resources)
		self.entries = {
			(entry.type, entry.identification, entry.field): entry for entry in iter_entries(language, types)
		}

	def run(self) -> ImportReport:
		for number, row in self.rows:
			try:
				self.import_row(row)
			except RowError as error:
				self.report.errors.append({"row": number, "message": str(error)})
		return self.report

	def import_row(self, row: dict):
		resource, entry, market = self.match(row)
		value = unescape_formula_injection(row["Translated content"])
		if not value:
			self.report.skipped += 1
		elif value == self.stored_value(entry, market):
			self.report.unchanged += 1
		else:
			self.write(resource, entry, value, market)
			self.report.updated += 1

	def match(self, row: dict) -> tuple[TranslatableResource, Entry, str]:
		if row["Locale"].casefold() != self.language.casefold():
			raise RowError(
				_("Locale {0} is not {1}, the language you import.").format(row["Locale"], self.language)
			)
		resource = self.resources.get(row["Type"])
		if not resource:
			raise RowError(_("{0} is not a type you can translate.").format(row["Type"]))
		if row["Field"] not in resource.fields:
			raise RowError(_("{0} is not a translatable field of {1}.").format(row["Field"], row["Type"]))
		entry = self.entries.get((row["Type"], row["Identification"], row["Field"]))
		if not entry:
			raise RowError(_("No {0} with identification {1}.").format(row["Type"], row["Identification"]))
		if row["Market"]:
			check_market(row["Market"])
		return resource, entry, row["Market"]

	def stored_value(self, entry: Entry, market: str) -> str:
		if market == SHOP_WIDE:
			return entry.translated
		filters = {
			"reference_doctype": self.resources[entry.type].doctype,
			"reference_name": entry.identification,
			"reference_field": entry.field,
			"language": self.language,
			"market": market,
		}
		return cstr(frappe.db.get_value(DOCTYPE, filters, "translated_value"))

	def write(self, resource: TranslatableResource, entry: Entry, value: str, market: str):
		# A refused save must not leave a half-written row or a toast behind for this row.
		messages = len(frappe.local.message_log)
		frappe.db.savepoint("import_translation_row")
		try:
			write_entry(resource, entry.identification, entry.field, self.language, value, market)
		except frappe.ValidationError as error:
			frappe.db.rollback(save_point="import_translation_row")
			del frappe.local.message_log[messages:]
			raise RowError(cstr(error) or _("The translation could not be saved.")) from error


def check_market(market: str):
	if not frappe.db.exists("DocType", MARKET_DOCTYPE):
		raise RowError(_("Markets are not available yet. Leave the Market column empty."))
	if not frappe.db.exists(MARKET_DOCTYPE, market):
		raise RowError(_("Market {0} does not exist.").format(market))


def read_rows(content: bytes | str) -> list[tuple[int, dict]]:
	"""(spreadsheet row number, {column: cell}) of each non-blank row. The header is row 1."""
	reader = csv.reader(io.StringIO(decode(content), newline=""))
	try:
		header = [cstr(cell).strip() for cell in next(reader, [])]
		if missing := [column for column in IMPORT_COLUMNS if column not in header]:
			frappe.throw(_("The file has no {0} column.").format(", ".join(missing)))
		rows = []
		for number, cells in enumerate(reader, start=2):
			if not any(cell.strip() for cell in cells):
				continue
			if len(rows) == MAX_IMPORT_ROWS:
				frappe.throw(_("Import at most {0} rows at a time.").format(MAX_IMPORT_ROWS))
			rows.append((number, read_cells(header, cells)))
	except csv.Error:
		frappe.throw(_("The file is not a valid CSV file."))
	return rows


def read_cells(header: list[str], cells: list[str]) -> dict:
	"""Key columns are trimmed; translated content is kept exactly as written."""
	row = dict(zip(header, cells, strict=False))
	return {
		column: row.get(column, "") if column == "Translated content" else row.get(column, "").strip()
		for column in IMPORT_COLUMNS
	}


def decode(content: bytes | str) -> str:
	if isinstance(content, str):
		return content.removeprefix("﻿")
	try:
		return content.decode("utf-8-sig")
	except UnicodeDecodeError:
		frappe.throw(_("Save the file as CSV in UTF-8 and upload it again."))


# Doctype resources: the only code here that knows a resource is a doctype.
# Swap these two for the generic resource interface (list entries per language, write) when it lands.


def iter_entries(language: str, types: Iterable[str] | None = None) -> Iterator[Entry]:
	for resource in get_translatable_resources():
		if types is None or resource.type in types:
			yield from iter_doctype_entries(resource, language)


def write_entry(
	resource: TranslatableResource, name: str, fieldname: str, language: str, value: str, market: str
):
	register(resource.doctype, name, fieldname, language, value, market)


def iter_doctype_entries(resource: TranslatableResource, language: str) -> Iterator[Entry]:
	meta = frappe.get_meta(resource.doctype)
	columns = [fieldname for fieldname in resource.fields if meta.has_field(fieldname)]
	records = frappe.get_all(resource.doctype, fields=["name", *columns], order_by="name asc")
	for batch in create_batch(records, BATCH_SIZE):
		sources = get_sources(resource.doctype, batch, list(resource.fields))
		names = [record.name for record in batch]
		translations = fetch_translations(resource.doctype, names, list(resource.fields), language)
		for record, source in zip(batch, sources, strict=True):
			for fieldname in resource.fields:
				translated, source_hash = translations.get((record.name, fieldname)) or ("", None)
				yield Entry(
					type=resource.type,
					identification=cstr(record.name),
					field=fieldname,
					status=get_status(source[fieldname], cstr(translated), source_hash),
					default=source[fieldname],
					translated=cstr(translated),
				)


def get_status(source: str, translated: str, source_hash: str | None) -> str:
	if not translated:
		return MISSING
	return CURRENT if source_hash == get_source_hash(source) else OUTDATED
