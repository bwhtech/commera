"""Copy each Item's Arabic name and description into Arabic Content Translation rows, then drop the fields.
Both were Custom Fields made on each site, so a new site has neither and the patch does nothing."""

import csv
import io

import frappe
from frappe.custom.doctype.custom_field.custom_field import delete_custom_fields
from frappe.utils import cstr, now, today
from frappe.utils.html_utils import sanitize_html

from commera.localization.content import DOCTYPE, SHOP_WIDE, get_source_hash, get_sources

LANGUAGE = "ar"
PRODUCT = "Style Attribute Variant"
SIZE = "Color Size Item"
SETTINGS = "Commera Settings"
# Each Item field and the product field it translates. A product page shows its Item's description.
FIELDS = {"custom_item_name_ar": "display_name", "custom_description_ar": "description"}
COLUMNS = {field: column for column, field in FIELDS.items()}
BATCH_SIZE = 500
ARCHIVE_PREFIX = "legacy-item-arabic-unmigrated"
# Characters per archive part. Arabic text takes two bytes a character in UTF-8.
ARCHIVE_PART_SIZE = 5_000_000
ARCHIVE_TITLE = "Item Arabic values archived before the fields were dropped"
ARCHIVE_HEADER = ("item_code", "item_name", *FIELDS, "reason")
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


def execute():
	columns = [field for field in FIELDS if frappe.db.has_column("Item", field)]
	if columns:
		ItemArabicMigration(columns).run()
	delete_custom_fields({"Item": list(FIELDS)})
	frappe.db.delete("Variant Field", {"field_name": ("in", list(FIELDS))})
	if columns:
		frappe.db.drop_columns("Item", columns)
		# has_column reads a cached column list that MariaDB DDL leaves stale.
		frappe.client_cache.delete_value("table_columns::tabItem")
	if columns or has_arabic_translations():
		from commera.search.build import enqueue_full_rebuild

		# Bulk inserts skip the reindex hook. A retry after the drop still has the rows to index.
		enqueue_full_rebuild(deduplicate=True)


def has_arabic_translations() -> bool:
	filters = {"reference_doctype": PRODUCT, "language": LANGUAGE, "reference_field": ("in", list(COLUMNS))}
	return bool(frappe.db.exists(DOCTYPE, filters))


class ItemArabicMigration:
	"""Copies the Arabic values one page of Items at a time. What it cannot copy goes to an archive."""

	def __init__(self, columns: list[str]):
		self.columns = columns
		self.fields = [FIELDS[column] for column in columns]
		self.archive = Archive()

	def run(self):
		for page in self.read_pages():
			self.migrate({row.name: row for row in page})
		self.archive.save()
		# The column drop that follows is final, so the copies and the archive are committed first.
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	def read_pages(self):
		"""Items with an Arabic value, in pages ordered by name."""
		item = frappe.qb.DocType("Item")
		has_value = None
		for column in self.columns:
			condition = item[column].isnotnull() & (item[column] != "")
			has_value = condition if has_value is None else has_value | condition
		query = (
			frappe.qb.from_(item)
			.select(item.name, item.item_name, *(item[column] for column in self.columns))
			.where(has_value)
			.orderby(item.name)
			.limit(BATCH_SIZE)
		)
		last = None
		while page := (query if last is None else query.where(item.name > last)).run(as_dict=True):
			yield page
			last = page[-1].name

	def migrate(self, items: dict):
		reasons = {name: [] for name in items}
		templates = self.copy(items, reasons)
		sizes = self.check_sizes(items, reasons)
		for name, row in items.items():
			if name not in templates and name not in sizes:
				reasons[name].append("no product uses this Item")
			if reasons[name]:
				self.archive.add(row, reasons[name])

	def copy(self, items: dict, reasons: dict) -> set[str]:
		"""Write each Item's values onto the products it is the template of. Returns those Items."""
		products = frappe.get_all(
			PRODUCT,
			filters={"item_style": ("in", list(items))},
			fields=["name", "item_style", "display_name"],
		)
		if not products:
			return set()
		sources = get_sources(PRODUCT, products, self.fields)
		existing = read_existing([product.name for product in products], self.fields)
		timestamp = now()
		rows = []
		for product, source in zip(products, sources, strict=True):
			for field, value in arabic_values(items[product.item_style], self.columns).items():
				clean, kept = sanitize(value), existing.get((product.name, field))
				# The products get the sanitised value, so the archive keeps the raw one.
				if clean != value:
					reasons[product.item_style].append(f"{COLUMNS[field]}: sanitised on copy")
				if kept is None:
					rows.append(make_row(product.name, field, clean, source[field], timestamp))
				elif kept != clean:
					reasons[product.item_style].append(
						f"{COLUMNS[field]}: a product kept another translation"
					)
		if rows:
			frappe.db.bulk_insert(DOCTYPE, ROW_FIELDS, rows, ignore_duplicates=True)
		return {product.item_style for product in products}

	def check_sizes(self, items: dict, reasons: dict) -> set[str]:
		"""Size Items whose values differ from their template's, which is what the product got."""
		size, product = frappe.qb.DocType(SIZE), frappe.qb.DocType(PRODUCT)
		links = (
			frappe.qb.from_(size)
			.join(product)
			.on(size.parent == product.name)
			.select(size.item_code, product.item_style)
			.where(size.item_code.isin(list(items)) & (size.parenttype == PRODUCT))
			.distinct()
			.run(as_dict=True)
		)
		links = [link for link in links if link.item_code != link.item_style]
		templates = self.read_templates({link.item_style for link in links if link.item_style})
		for link in links:
			template = templates.get(link.item_style, {})
			for field, value in arabic_values(items[link.item_code], self.columns).items():
				if template.get(field) != value:
					reasons[link.item_code].append(
						f"{COLUMNS[field]} differs from template {link.item_style}"
					)
		return {link.item_code for link in links}

	def read_templates(self, names: set[str]) -> dict[str, dict]:
		if not names:
			return {}
		item = frappe.qb.DocType("Item")
		rows = (
			frappe.qb.from_(item)
			.select(item.name, *(item[column] for column in self.columns))
			.where(item.name.isin(list(names)))
			.run(as_dict=True)
		)
		return {row.name: arabic_values(row, self.columns) for row in rows}


class Archive:
	"""Private CSVs on Commera Settings of the values the patch did not copy.
	A part is saved when it reaches ARCHIVE_PART_SIZE, so memory stays bounded."""

	def __init__(self):
		self.count = 0
		self.files = []
		self.start_part()

	def add(self, row, reasons: list[str]):
		values = (cstr(row.get(column)) for column in FIELDS)
		self.writer.writerow((row.name, row.item_name, *values, "; ".join(dict.fromkeys(reasons))))
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
			f"Items with Arabic values not copied into Content Translation: {self.count}. "
			f"The values are in the private files {', '.join(self.files)} attached to {SETTINGS}."
		)
		frappe.log_error(ARCHIVE_TITLE, message, SETTINGS, SETTINGS)
		print(message)

	def start_part(self):
		self.rows = 0
		self.buffer = io.StringIO()
		self.writer = csv.writer(self.buffer)
		self.writer.writerow(ARCHIVE_HEADER)

	def save_part(self):
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{ARCHIVE_PREFIX}-{today()}-{len(self.files) + 1}.csv",
				"attached_to_doctype": SETTINGS,
				"attached_to_name": SETTINGS,
				"is_private": 1,
				"content": self.buffer.getvalue(),
			}
		)
		file.flags.skip_file_size_check = True
		file.insert(ignore_permissions=True)
		self.files.append(file.file_name)


def arabic_values(row, columns: list[str]) -> dict[str, str]:
	"""{product field: value} of the row's non-blank Arabic values."""
	return {FIELDS[column]: value for column in columns if (value := cstr(row.get(column)).strip())}


def read_existing(names: list[str], fields: list[str]) -> dict[tuple[str, str], str]:
	"""{(product, field): value} of the shop-wide Arabic translations already written. The patch keeps them."""
	rows = frappe.get_all(
		DOCTYPE,
		filters={
			"reference_doctype": PRODUCT,
			"reference_name": ("in", names),
			"reference_field": ("in", fields),
			"language": LANGUAGE,
			"market": SHOP_WIDE,
		},
		fields=["reference_name", "reference_field", "translated_value"],
	)
	return {(row.reference_name, row.reference_field): cstr(row.translated_value) for row in rows}


def make_row(product: str, field: str, value: str, source: str, timestamp: str) -> tuple:
	"""A Content Translation row of a sanitised value, current against the source now."""
	user = frappe.session.user
	return (
		frappe.generate_hash(length=10),
		timestamp,
		timestamp,
		user,
		user,
		LANGUAGE,
		SHOP_WIDE,
		PRODUCT,
		product,
		field,
		value,
		get_source_hash(source),
	)


def sanitize(value: str) -> str:
	# Document._sanitize_content cleans only values that look like HTML.
	return sanitize_html(value) if "<" in value or ">" in value else value
