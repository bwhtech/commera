"""Translation exchange: one language's translations as a CSV in Shopify's column shape, and an
import that writes such a file back through `register()`, one row at a time."""

import csv
import io
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field

import frappe
from frappe import _
from frappe.utils import create_batch, cstr

from commera.localization.content import (
	BATCH_SIZE,
	CURRENT,
	DOCTYPE,
	MISSING,
	OUTDATED,
	SHOP_WIDE,
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
MAX_FILE_SIZE = 10 * 1024 * 1024
# A spreadsheet runs a cell that starts with one of these. The apostrophe is here so the quote reverses.
FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r", "'")
# Markets arrive with #450. Until that doctype exists, a row for a market is an error.
MARKET_DOCTYPE = "Commera Market"


@dataclass(frozen=True)
class Entry:
	"""One translatable field of one record, in one language."""

	type: str
	identification: str
	field: str
	market: str
	status: str
	default: str
	translated: str

	@property
	def key(self) -> tuple[str, str, str, str]:
		return (self.type, self.identification, self.field, self.market)

	def as_row(self, language: str) -> list[str]:
		return [
			self.type,
			self.identification,
			self.field,
			language,
			self.market,
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
	"""Every field with a source or a translation, shop-wide and per market. Cells are quoted against
	formulas (OWASP) by `encode_cell`, which the import reverses."""
	language = get_exchange_language(language)
	buffer = io.StringIO()
	writer = csv.writer(buffer)
	writer.writerow(COLUMNS)
	for entry in iter_entries(language):
		if entry.default or entry.translated:
			writer.writerow([encode_cell(cell) for cell in entry.as_row(language)])
	return buffer.getvalue()


def import_csv(content: bytes | str, language: str) -> ImportReport:
	return TranslationImport(read_rows(content), get_exchange_language(language)).run()


class TranslationImport:
	"""Matches each row on type, identification, field, locale and market, and writes the changed ones.
	A bad row, or a repeat of a key, becomes an error in the report and the next row is read."""

	def __init__(self, rows: list[tuple[int, dict]], language: str):
		self.rows = rows
		self.language = language
		self.report = ImportReport()
		self.seen = {}
		self.resources = {resource.type: resource for resource in get_translatable_resources()}
		types = {row["Type"] for _number, row in rows} & set(self.resources)
		# A snapshot is safe to compare against because each key is imported at most once.
		self.entries = {entry.key: entry for entry in iter_entries(language, types)}

	def run(self) -> ImportReport:
		for number, row in self.rows:
			try:
				self.import_row(number, row)
			except RowError as error:
				self.report.errors.append({"row": number, "message": str(error)})
		return self.report

	def import_row(self, number: int, row: dict):
		if row["Market"]:
			row["Market"] = canonical_market(row["Market"])
		self.check_duplicate(number, row)
		resource, entry, market = self.match(row)
		value = row["Translated content"]
		if not value:
			self.report.skipped += 1
		elif value == self.stored_value(entry, market):
			self.report.unchanged += 1
		else:
			self.write(resource, entry, value, market)
			self.report.updated += 1

	def check_duplicate(self, number: int, row: dict):
		key = (row["Type"], row["Identification"], row["Field"], row["Locale"].casefold(), row["Market"])
		if first := self.seen.get(key):
			raise RowError(
				_("Row {0} already has this type, identification, field and market.").format(first)
			)
		self.seen[key] = number

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
		entry = self.find_entry(row)
		if not entry:
			raise RowError(_("No {0} with identification {1}.").format(row["Type"], row["Identification"]))
		return resource, entry, row["Market"]

	def find_entry(self, row: dict) -> Entry | None:
		key = (row["Type"], row["Identification"], row["Field"], SHOP_WIDE)
		if entry := self.entries.get(key):
			return entry
		# decode_cell removed an apostrophe the record's own name starts with.
		if row["Identification"].startswith(FORMULA_TRIGGERS):
			return self.entries.get((row["Type"], "'" + row["Identification"], row["Field"], SHOP_WIDE))
		return None

	def stored_value(self, entry: Entry, market: str) -> str:
		stored = self.entries.get((entry.type, entry.identification, entry.field, market))
		return stored.translated if stored else ""

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


def canonical_market(market: str) -> str:
	"""The market's stored name, so `inr` and `INR` are one key for duplicates and lookups."""
	if not frappe.db.exists("DocType", MARKET_DOCTYPE):
		raise RowError(_("Markets are not available yet. Leave the Market column empty."))
	if not (name := frappe.db.get_value(MARKET_DOCTYPE, market, "name")):
		raise RowError(_("Market {0} does not exist.").format(market))
	return name


# Python's default of 128 KB refuses long pages. Set once: a scoped change races other threads.
csv.field_size_limit(max(csv.field_size_limit(), MAX_FILE_SIZE))


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
	"""Key columns are trimmed; translated content is kept exactly as written. Both are decoded."""
	row = dict(zip(header, cells, strict=False))
	values = {column: row.get(column, "") for column in IMPORT_COLUMNS}
	return {
		column: decode_cell(value if column == "Translated content" else value.strip())
		for column, value in values.items()
	}


def encode_cell(value: str) -> str:
	return "'" + value if value.startswith(FORMULA_TRIGGERS) else value


def decode_cell(value: str) -> str:
	"""Reverses `encode_cell`. Any other leading apostrophe was typed and stays."""
	return value[1:] if value.startswith("'") and value[1:].startswith(FORMULA_TRIGGERS) else value


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


def read_records(doctype: str, meta, columns: list[str]) -> list:
	# A Single has no rows to list: its one record is named after the doctype.
	if meta.issingle:
		doc = frappe.get_cached_doc(doctype)
		return [frappe._dict(name=doctype, **{column: doc.get(column) for column in columns})]
	return frappe.get_all(doctype, fields=["name", *columns], order_by="name asc")


def iter_doctype_entries(resource: TranslatableResource, language: str) -> Iterator[Entry]:
	meta = frappe.get_meta(resource.doctype)
	columns = [fieldname for fieldname in resource.fields if meta.has_field(fieldname)]
	for batch in create_batch(read_records(resource.doctype, meta, columns), BATCH_SIZE):
		sources = get_sources(resource.doctype, batch, list(resource.fields))
		names = [cstr(record.name) for record in batch]
		translations = fetch_all_translations(resource.doctype, names, list(resource.fields), language)
		for name, source in zip(names, sources, strict=True):
			for fieldname in resource.fields:
				markets = translations.get((name, fieldname), {})
				for market in [SHOP_WIDE, *sorted(set(markets) - {SHOP_WIDE})]:
					translated, source_hash = markets.get(market) or ("", None)
					yield Entry(
						type=resource.type,
						identification=name,
						field=fieldname,
						market=market,
						status=get_status(source[fieldname], translated, source_hash),
						default=source[fieldname],
						translated=translated,
					)


def fetch_all_translations(doctype: str, names: list[str], fields: list[str], language: str) -> dict:
	"""{(name, field): {market: (translated value, source hash)}}, shop-wide and every market."""
	rows = frappe.get_all(
		DOCTYPE,
		filters={
			"reference_doctype": doctype,
			"reference_name": ("in", names),
			"reference_field": ("in", fields),
			"language": language,
		},
		fields=["reference_name", "reference_field", "market", "translated_value", "source_hash"],
	)
	translations = {}
	for row in rows:
		markets = translations.setdefault((row.reference_name, row.reference_field), {})
		markets[cstr(row.market)] = (cstr(row.translated_value), row.source_hash)
	return translations


def get_status(source: str, translated: str, source_hash: str | None) -> str:
	if not translated:
		return MISSING
	return CURRENT if source_hash == get_source_hash(source) else OUTDATED
