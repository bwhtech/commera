"""Translation exchange: one language's translations as a CSV in Shopify's column shape, and an
import that writes such a file back one row at a time. Both go through the resource interface only."""

import csv
import io
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from itertools import batched

import frappe
from frappe import _
from frappe.utils import cstr

from commera.localization.content import BATCH_SIZE, SHOP_WIDE, find_market_key
from commera.localization.languages import StorefrontLanguages
from commera.localization.resources import (
	TranslatableResource,
	TranslationEntry,
	get_translatable_resources,
)

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


@dataclass(frozen=True)
class Entry:
	"""One translatable field of one record, in one language, as a CSV row names it."""

	type: str
	identification: str
	field: str
	market: str
	status: str
	default: str
	translated: str

	@classmethod
	def from_translation(cls, entry: TranslationEntry) -> "Entry":
		return cls(
			type=entry.resource,
			identification=entry.name,
			field=entry.field,
			market=entry.market,
			status=entry.status,
			default=entry.source,
			translated=entry.value,
		)

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
	"""Every field with a source or a stored translation, shop-wide and per market, of every resource.
	Cells are quoted against formulas (OWASP) by `encode_cell`, which the import reverses."""
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
	"""Matches each row on type, identification, field, locale and market, and writes the changed ones
	through its resource. A bad row, or a repeat of a key, becomes an error in the report."""

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
		row["Market"] = canonical_market(row["Market"])
		self.check_duplicate(number, row)
		resource = self.match(row)
		entry, name = self.find_record(resource, row)
		value, market = row["Translated content"], row["Market"]
		if not value:
			self.report.skipped += 1
		elif entry and value == self.stored_value(entry, market):
			self.report.unchanged += 1
		else:
			self.write(resource, name, row["Field"], value, market)
			self.report.updated += 1

	def check_duplicate(self, number: int, row: dict):
		key = (row["Type"], row["Identification"], row["Field"], row["Locale"].casefold(), row["Market"])
		if first := self.seen.get(key):
			raise RowError(
				_("Row {0} already has this type, identification, field and market.").format(first)
			)
		self.seen[key] = number

	def match(self, row: dict) -> TranslatableResource:
		if row["Locale"].casefold() != self.language.casefold():
			raise RowError(
				_("Locale {0} is not {1}, the language you import.").format(row["Locale"], self.language)
			)
		resource = self.resources.get(row["Type"])
		if not resource:
			raise RowError(_("{0} is not a type you can translate.").format(row["Type"]))
		return resource

	def find_record(self, resource: TranslatableResource, row: dict) -> tuple[Entry | None, str]:
		"""The row's exported entry, if any, and its record name. An unknown record or field is an
		error even with nothing to import, as the export never names one."""
		if entry := self.find_entry(row):
			return entry, entry.identification
		for name in candidate_names(row["Identification"]):
			# A field the export had no row for, e.g. one without source text or translation.
			if resource.exists(name, row["Field"]):
				return None, name
		raise RowError(
			_("No {0} with identification {1} has a translatable field {2}.").format(
				row["Type"], row["Identification"], row["Field"]
			)
		)

	def find_entry(self, row: dict) -> Entry | None:
		for name in candidate_names(row["Identification"]):
			if entry := self.entries.get((row["Type"], name, row["Field"], SHOP_WIDE)):
				return entry
		return None

	def stored_value(self, entry: Entry, market: str) -> str:
		stored = self.entries.get((entry.type, entry.identification, entry.field, market))
		return stored.translated if stored else ""

	def write(self, resource: TranslatableResource, name: str, fieldname: str, value: str, market: str):
		# A refused save must not leave a half-written row or a toast behind for this row.
		messages = len(frappe.local.message_log)
		frappe.db.savepoint("import_translation_row")
		try:
			resource.write(name, fieldname, self.language, value, market)
		except (frappe.ValidationError, frappe.PermissionError) as error:
			frappe.db.rollback(save_point="import_translation_row")
			del frappe.local.message_log[messages:]
			raise RowError(cstr(error) or _("The translation could not be saved.")) from error


def candidate_names(identification: str) -> list[str]:
	"""decode_cell removes an apostrophe a record's own name may start with."""
	if identification.startswith(FORMULA_TRIGGERS):
		return [identification, "'" + identification]
	return [identification]


def canonical_market(market: str) -> str:
	"""The market's stored name, so `gulf` and `Gulf` are one key for duplicates and lookups.
	`primary` is the shop-wide row, as the primary market is the store itself."""
	name = find_market_key(market)
	if name is None:
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


def iter_entries(language: str, types: Iterable[str] | None = None) -> Iterator[Entry]:
	"""Each resource's entries, sourceless ones too, each shop-wide one followed by its market ones."""
	for resource in get_translatable_resources():
		if types is not None and resource.type not in types:
			continue
		for batch in batched(resource.iter_entries(language, include_sourceless=True), BATCH_SIZE):
			markets = resource.get_market_entries(list(batch), language)
			for entry in batch:
				yield Entry.from_translation(entry)
				for market_entry in markets.get((entry.name, entry.field), []):
					yield Entry.from_translation(market_entry)
