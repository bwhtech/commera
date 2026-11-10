"""Shared steps of the patches that move legacy Arabic fields into Content Translation rows:
the row writer and the private archive of the values a patch could not copy verbatim."""

import csv
import io

import frappe
from frappe.query_builder.functions import Length
from frappe.utils import cstr, now, today
from frappe.utils.html_utils import sanitize_html

from commera.localization.content import DOCTYPE, SHOP_WIDE, get_source_hash

LANGUAGE = "ar"
SETTINGS = "Commera Settings"
# Characters per archive part. Arabic text takes two bytes a character in UTF-8.
ARCHIVE_PART_SIZE = 5_000_000
ROW_FIELDS = (
	"name",
	"creation",
	"modified",
	"owner",
	"modified_by",
	"language",
	"market",
	"reference_doctype",
	"reference_name",
	"reference_field",
	"translated_value",
	"source_hash",
)


class TranslationCopy:
	"""Arabic values to write onto one doctype's records. A record keeps a translation it already has."""

	def __init__(self, doctype: str):
		self.doctype = doctype
		self.rows = []
		self.timestamp = now()

	def add(self, name: str, field: str, raw, source, existing: dict) -> list[str]:
		"""Queue the trimmed, sanitised value. Returns why it was not copied verbatim, if it was not.
		Whitespace alone translates nothing, so it is neither copied nor archived."""
		value = cstr(raw).strip()
		if not value:
			return []
		clean, kept = sanitize(value), existing.get((name, field))
		reasons = ["sanitised on copy"] if clean != value else []
		if kept is None:
			self.rows.append(self.make_row(name, field, clean, source))
		elif kept != clean:
			reasons.append("a translation was already saved")
		return reasons

	def insert(self):
		if self.rows:
			frappe.db.bulk_insert(DOCTYPE, ROW_FIELDS, self.rows, ignore_duplicates=True)
		self.rows = []

	def make_row(self, name: str, field: str, value: str, source) -> tuple:
		user = frappe.session.user
		return (
			frappe.generate_hash(length=10),
			self.timestamp,
			self.timestamp,
			user,
			user,
			LANGUAGE,
			SHOP_WIDE,
			self.doctype,
			name,
			field,
			value,
			get_source_hash(source),
		)


class Archive:
	"""Private CSVs on Commera Settings of the values a patch did not copy.
	A part is saved once it passes ARCHIVE_PART_SIZE characters, an approximate bound: one huge row can exceed it."""

	def __init__(self, prefix: str, title: str, header: tuple[str, ...], label: str):
		self.prefix, self.title, self.header, self.label = prefix, title, header, label
		self.count = 0
		self.files = []
		self.start_part()

	def add(self, *values):
		self.writer.writerow([cstr(value) for value in values])
		self.count += 1
		self.rows += 1
		if self.buffer.tell() >= ARCHIVE_PART_SIZE:
			self.save_part()
			self.start_part()

	def save(self):
		"""Save the last part, then log the name of every part."""
		if self.rows:
			self.save_part()
		if not self.files:
			return
		message = (
			f"{self.label} not copied into Content Translation: {self.count}. "
			f"The values are in the private files {', '.join(self.files)} attached to {SETTINGS}."
		)
		frappe.log_error(self.title, message, SETTINGS, SETTINGS)
		print(message)

	def start_part(self):
		self.rows = 0
		self.buffer = io.StringIO()
		self.writer = csv.writer(self.buffer)
		self.writer.writerow(self.header)

	def save_part(self):
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{self.prefix}-{today()}-{len(self.files) + 1}.csv",
				"attached_to_doctype": SETTINGS,
				"attached_to_name": SETTINGS,
				"is_private": 1,
				"content": self.buffer.getvalue(),
			}
		)
		file.flags.skip_file_size_check = True
		file.insert(ignore_permissions=True)
		self.files.append(file.file_name)


def read_existing(doctype: str, names: list[str], fields: list[str]) -> dict[tuple[str, str], str]:
	"""{(record, field): value} of the shop-wide Arabic translations already written. The patches keep them."""
	if not names:
		return {}
	rows = frappe.get_all(
		DOCTYPE,
		filters={
			"reference_doctype": doctype,
			"reference_name": ("in", names),
			"reference_field": ("in", fields),
			"language": LANGUAGE,
			"market": SHOP_WIDE,
		},
		fields=["reference_name", "reference_field", "translated_value"],
	)
	return {(row.reference_name, row.reference_field): cstr(row.translated_value) for row in rows}


def has_value(column):
	# Byte length, not `!= ""`: the collation treats some characters as equal to "".
	return Length(column) > 0


def commit():
	# The drop that follows is final, so the copies and the archive are committed first.
	frappe.db.commit()  # nosemgrep: frappe-manual-commit


def sanitize(value: str) -> str:
	# Document._sanitize_content cleans only values that look like HTML.
	return sanitize_html(value) if "<" in value or ">" in value else value
