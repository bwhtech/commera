# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import math
import zipfile

import frappe
from frappe import _
from frappe.utils.csvutils import read_csv_content
from frappe.utils.data import cstr, flt
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file
from openpyxl.utils.exceptions import InvalidFileException

from commera.api.admin.catalog import (
	DEFAULT_OPTION_ATTRIBUTE,
	DEFAULT_OPTION_VALUE,
	get_collection,
	get_new_product_title_limit,
)

TEMPLATE_HEADERS = [
	"Product Title",
	"Collection",
	"Color",
	"Size",
	"Price",
	"Original price",
	"Stock",
]

# Every field an importer accepts, in TEMPLATE_HEADERS order. The first synonym is the field's own
# name; the rest are other spellings a file's header row is matched against (see suggest_mapping).
FIELD_SYNONYMS = {
	"title": ["product title", "title", "product name", "name"],
	"collection": ["collection", "category", "item group"],
	"color": ["color", "colour"],
	"size": ["size"],
	"sale_price": ["price", "selling price", "sale price", "discounted price"],
	"compare_at_price": [
		"original price",
		"compare at price",
		"compareat price",
		"mrp",
		"list price",
		"regular price",
	],
	"stock": ["stock", "quantity", "qty", "stock quantity", "qty on hand", "inventory"],
}
FIELD_LABELS = dict(zip(FIELD_SYNONYMS, TEMPLATE_HEADERS, strict=True))
# Collection is required too, unless the merchant picks one collection for every row instead.
REQUIRED_FIELDS = ["title", "sale_price"]

# Older Commera templates and many shops export "Price" next to a "Discounted price": there the plain
# Price is the struck-through one, and reading it as what the shopper pays would overcharge.
DISCOUNT_HEADERS = {"discounted price", "sale price"}
PREVIEW_ROWS = 3


def normalize_header(text):
	return "".join(ch for ch in cstr(text).strip().casefold() if ch.isalnum() or ch == " ").strip()


# What openpyxl raises for bytes that are not a workbook: no zip at all (a renamed PDF, an old .xls),
# or a zip without a workbook inside. Anything else is a bug and is left to reach the error log.
NOT_A_WORKBOOK_ERRORS = (zipfile.BadZipFile, InvalidFileException, KeyError)


def read_uploaded_rows(file_url):
	"""The file's raw grid, header row included, blank rows dropped."""
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	rows = read_spreadsheet(file_doc)
	if rows is None:
		frappe.throw(
			_("This file is not a readable Excel or CSV file. Save it again from Excel, or export it as CSV.")
		)
	return [row for row in rows if any(cstr(cell).strip() for cell in row)]


def read_spreadsheet(file_doc):
	"""The file's rows, or None when it is not what its name says. get_content() returns str for text and
	bytes otherwise, which tells a CSV from a workbook before the wrong parser trips over it."""
	content = file_doc.get_content()
	if cstr(file_doc.file_name).lower().endswith(".csv"):
		return read_csv_content(content) if isinstance(content, str) else None
	if not isinstance(content, bytes) or not content:
		return None
	try:
		return read_xlsx_file_from_attached_file(fcontent=content)
	except NOT_A_WORKBOOK_ERRORS:
		return None


def get_contained_field(text, taken):
	"""The free field whose longest synonym appears in the header as whole words, so "Variant Compare At
	Price" is the original price rather than the price."""
	padded = f" {text} "
	best_field, best_length = None, 0
	for field, synonyms in FIELD_SYNONYMS.items():
		if field in taken:
			continue
		for synonym in synonyms:
			if f" {synonym} " in padded and len(synonym) > best_length:
				best_field, best_length = field, len(synonym)
	return best_field


def get_exact_field(text, taken, primary_only):
	for field, synonyms in FIELD_SYNONYMS.items():
		if field not in taken and text in (synonyms[:1] if primary_only else synonyms):
			return field
	return None


def suggest_mapping(headers):
	"""Best-guess header -> field, each field used once: an exact name is "high", a known spelling "medium",
	and a header that only contains one ("Variant Size") "low", which the Map step asks about."""
	normalized = {header: normalize_header(header) for header in headers}
	mapping = dict.fromkeys(headers, "")
	confidence = dict.fromkeys(headers, "none")
	matchers = (
		("high", lambda text, taken: get_exact_field(text, taken, primary_only=True)),
		("medium", lambda text, taken: get_exact_field(text, taken, primary_only=False)),
		("low", get_contained_field),
	)
	for level, matcher in matchers:
		for header in headers:
			taken = set(mapping.values())
			field = not mapping[header] and matcher(normalized[header], taken)
			if field:
				mapping[header], confidence[header] = field, level

	swap_price_pair(mapping, confidence, normalized)
	return mapping, confidence


def swap_price_pair(mapping, confidence, normalized):
	"""A plain Price next to a discounted price is the original price; a lone original price column is
	what the shopper pays, since nothing can be crossed out without a price to charge."""
	fields = set(mapping.values())
	discount_header = next(
		(header for header, text in normalized.items() if text in DISCOUNT_HEADERS and not mapping[header]),
		None,
	)
	price_header = next((header for header, field in mapping.items() if field == "sale_price"), None)
	if discount_header and price_header and "compare_at_price" not in fields:
		mapping[price_header], confidence[price_header] = "compare_at_price", "medium"
		mapping[discount_header], confidence[discount_header] = "sale_price", "medium"
	elif "sale_price" not in fields and "compare_at_price" in fields:
		header = next(header for header, field in mapping.items() if field == "compare_at_price")
		mapping[header] = "sale_price"


def read_column_mapping(headers, column_mapping):
	mapping = {header: cstr(column_mapping.get(header)) for header in headers}
	unknown = sorted({field for field in mapping.values() if field and field not in FIELD_SYNONYMS})
	if unknown:
		frappe.throw(_("These are not fields a product can be imported into: {0}").format(", ".join(unknown)))
	return mapping


def get_missing_fields(mapping, default_collection):
	required = REQUIRED_FIELDS if default_collection else [*REQUIRED_FIELDS, "collection"]
	return [field for field in required if field not in mapping.values()]


def parse_and_validate(
	file_url: str, column_mapping: dict | None = None, default_collection: str | None = None
):
	"""A dry run shared by the Review step and run_import(): each row with its issue, or none. Unmatched
	required fields answer with `missing` set and no rows checked, for the Map step."""
	rows = read_uploaded_rows(file_url)
	if not rows:
		frappe.throw(_("Your file has no rows. Add a header row and your products, then upload it again."))

	headers = [cstr(cell) for cell in rows[0]]
	data_rows = rows[1:]
	suggested_mapping, confidence = suggest_mapping(headers)
	mapping = read_column_mapping(headers, column_mapping) if column_mapping else dict(suggested_mapping)
	default_collection = get_collection(default_collection) if cstr(default_collection).strip() else None
	missing = get_missing_fields(mapping, default_collection)

	checker = RowChecker(headers, mapping, default_collection)
	parsed_rows = [] if missing else [checker.check(row, offset + 2) for offset, row in enumerate(data_rows)]
	return {
		"headers": headers,
		"mapping": mapping,
		"suggested_mapping": suggested_mapping,
		"confidence": confidence,
		"missing": missing,
		"preview": [pad_row(row, len(headers)) for row in data_rows[:PREVIEW_ROWS]],
		"samples": get_samples(headers, data_rows),
		"rows": parsed_rows,
		"counts": get_counts(parsed_rows, len(data_rows)),
	}


def pad_row(row, width):
	return [cstr(cell) for cell in row[:width]] + [""] * (width - len(row))


def get_samples(headers, data_rows):
	"""The first value under each header, shown in the Map step so a column is recognisable by its data."""
	return {
		header: next(
			(cstr(row[index]) for row in data_rows if index < len(row) and cstr(row[index]).strip()), ""
		)
		for index, header in enumerate(headers)
	}


def get_counts(parsed_rows, total):
	groups = group_valid_rows(parsed_rows)
	return {
		"total": total,
		"errors": sum(1 for row in parsed_rows if is_error(row)),
		"warnings": sum(1 for row in parsed_rows if row["issue"] and row["issue"]["level"] == "warning"),
		"ready": sum(1 for row in parsed_rows if not is_error(row)),
		"products": len(groups),
		# A product with no color and no size is one thing to buy, not a variant.
		"variants": sum(len(group["rows"]) for group in groups if group_has_options(group)),
	}


def is_error(row):
	return bool(row["issue"]) and row["issue"]["level"] == "error"


def group_has_options(group):
	return any(row["color"] or row["size"] for row in group["rows"])


def error(text):
	return {"level": "error", "text": text}


def warning(text):
	return {"level": "warning", "text": text}


class RowChecker:
	"""Reads one row at a time and gives it its first problem. Rows sharing a title are one product,
	so each row is also checked against the first clean row of its product and of its color."""

	def __init__(self, headers, mapping, default_collection):
		self.default_collection = default_collection
		self.column_index_by_field = {}
		for index, header in enumerate(headers):
			if mapping.get(header):
				self.column_index_by_field.setdefault(mapping[header], index)
		self.seen_variants = {}
		self.product_first_row = {}
		self.color_first_row = {}
		self.collection_exists = {}
		self.title_taken = {}

	def cell(self, row, field):
		index = self.column_index_by_field.get(field)
		return row[index] if index is not None and index < len(row) else None

	def text(self, row, field):
		return cstr(self.cell(row, field)).strip()

	def check(self, row, row_number):
		parsed = {
			"row": row_number,
			"title": self.text(row, "title"),
			"collection": self.text(row, "collection") or cstr(self.default_collection),
			"color": self.text(row, "color"),
			"size": self.text(row, "size"),
		}
		issue = self.read_amounts(row, parsed)
		issue = issue or self.check_required(row, parsed) or self.check_title(parsed)
		# The original price is settled before the per-color check, so two sizes compare what is
		# actually written; a warning is given only when no row error follows it.
		price_warning = self.check_original_price(parsed)
		issue = issue or self.check_duplicate(parsed) or self.check_against_product(parsed) or price_warning
		parsed["issue"] = issue
		parsed["image_key"] = get_image_group_key(parsed["title"], parsed["color"])
		return parsed

	def read_amounts(self, row, parsed):
		"""Strict, because flt() turns "not-a-number" into 0.0 (an unpriced row) and float() reads "inf" and
		"nan". A bad amount is the row's error."""
		issue = None
		for field, label in (
			("sale_price", _("Price")),
			("compare_at_price", _("Original price")),
			("stock", _("Stock")),
		):
			raw = self.cell(row, field)
			parsed[field] = read_amount(raw)
			if parsed[field] is None:
				parsed[field] = 0
				issue = issue or error(_('{0} "{1}" is not a number.').format(label, raw))
		return issue

	def check_required(self, row, parsed):
		if not parsed["title"]:
			return error(_("Product title is missing."))
		if not parsed["collection"]:
			return error(_("Collection is missing."))
		if not self.has_collection(parsed["collection"]):
			return error(_('Collection "{0}" does not exist. Create it first.').format(parsed["collection"]))
		if not self.text(row, "sale_price"):
			return error(_("Price is missing."))
		# The same rule, in the same words, as the Add product dialog.
		if parsed["sale_price"] <= 0:
			return error(_("Enter a price above zero."))

	def check_title(self, parsed):
		"""The titles catalog.create_product refuses, caught here so Review never calls a row Ready
		that the run then turns down."""
		title = parsed["title"]
		if title.startswith("New Item"):
			return error(_('A product title cannot start with "New Item". Rename it in your file.'))
		# Color is the import's option axis (imports.OPTION_ATTRIBUTE); a row with none hangs on the hidden one.
		limit = get_new_product_title_limit(
			"Color" if parsed["color"] else DEFAULT_OPTION_ATTRIBUTE,
			[parsed["color"] or DEFAULT_OPTION_VALUE],
		)
		if len(title) > limit:
			return error(_("Use {0} characters or fewer for the title.").format(limit))
		if self.is_title_taken(title):
			return error(
				_(
					'A product called "{0}" is already in your store. Rename it in your file to add it.'
				).format(title)
			)

	def is_title_taken(self, title):
		key = title.casefold()
		if key not in self.title_taken:
			# An Item is named after its title, and names compare case-insensitively.
			self.title_taken[key] = bool(frappe.db.exists("Item", title))
		return self.title_taken[key]

	def has_collection(self, collection):
		if collection not in self.collection_exists:
			self.collection_exists[collection] = bool(frappe.db.exists("Item Group", collection))
		return self.collection_exists[collection]

	def check_original_price(self, parsed):
		"""An optional field never costs the seller a product: a bad original price is dropped with a
		warning, in the Add product dialog's words."""
		if parsed["compare_at_price"] and parsed["compare_at_price"] <= parsed["sale_price"]:
			parsed["compare_at_price"] = 0
			return warning(_("Original price must be higher than the price. It is left out."))

	def check_duplicate(self, parsed):
		key = (parsed["title"].casefold(), parsed["color"].casefold(), parsed["size"].casefold())
		if key in self.seen_variants:
			return error(
				_("Repeats row {0}, with the same title, color and size.").format(self.seen_variants[key])
			)
		self.seen_variants[key] = parsed["row"]

	def check_against_product(self, parsed):
		first = self.product_first_row.setdefault(parsed["title"].casefold(), parsed)
		if first is parsed:
			return self.check_against_color(parsed)
		title, row = parsed["title"], first["row"]
		if parsed["collection"] != first["collection"]:
			return error(
				_('Collection does not match row {0} of "{1}", which is in {2}.').format(
					row, title, first["collection"]
				)
			)
		if bool(parsed["color"]) != bool(first["color"]):
			return error(
				_('Row {0} of "{1}" differs. Give every row of a product a color, or none.').format(
					row, title
				)
			)
		if bool(parsed["size"]) != bool(first["size"]):
			return error(
				_('Row {0} of "{1}" differs. Give every row of a product a size, or none.').format(row, title)
			)
		return self.check_against_color(parsed)

	def check_against_color(self, parsed):
		"""Each color has one price for all its sizes (the product model); colors may differ."""
		key = (parsed["title"].casefold(), parsed["color"].casefold())
		first = self.color_first_row.setdefault(key, parsed)
		if first is parsed or get_prices(parsed) == get_prices(first):
			return None
		if parsed["color"]:
			return error(
				_('Price does not match row {0}. Every size of {1} in "{2}" has the same price.').format(
					first["row"], parsed["color"], parsed["title"]
				)
			)
		return error(
			_('Price does not match row {0}. Every size of "{1}" has the same price.').format(
				first["row"], parsed["title"]
			)
		)


def read_amount(raw):
	"""A finite number, 0 for an empty cell, or None for anything else."""
	if raw in (None, ""):
		return 0
	try:
		amount = float(cstr(raw).replace(",", "").strip())
	except (TypeError, ValueError):
		return None
	return flt(amount) if math.isfinite(amount) else None


def get_prices(row):
	return (row["sale_price"], row["compare_at_price"])


def group_valid_rows(parsed_rows):
	"""One entry per product title with zero error rows; only these are ever written."""
	groups = {}
	for row in parsed_rows:
		if is_error(row):
			continue
		group = groups.setdefault(
			row["title"].casefold(),
			{"title": row["title"], "collection": row["collection"], "rows": []},
		)
		group["rows"].append(row)
	return list(groups.values())


def get_image_group_key(title, color):
	"""Photos hang off the color-level Style Attribute Variant, not off a size, so the unit a photo
	belongs to is one color of one product group."""
	return f"{cstr(title).casefold()}::{cstr(color).casefold()}"
