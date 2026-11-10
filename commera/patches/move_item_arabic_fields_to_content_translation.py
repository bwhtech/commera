"""Copy each Item's Arabic name and description into Arabic Content Translation rows, then drop the fields.
Both were Custom Fields made on each site, so a new site has neither and the patch does nothing."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import delete_custom_fields
from frappe.utils import create_batch, cstr, now
from frappe.utils.html_utils import sanitize_html

from commera.localization.content import DOCTYPE, SHOP_WIDE, get_source_hash, get_sources

LANGUAGE = "ar"
PRODUCT = "Style Attribute Variant"
# Each Item field and the product field it translates. A product page shows its Item's description.
FIELDS = {"custom_item_name_ar": "display_name", "custom_description_ar": "description"}
BATCH_SIZE = 500
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
	copied = sum(copy_batch(batch, columns) for batch in create_batch(read_arabic_items(columns), BATCH_SIZE))
	# DDL commits the copied rows first, so the fields go only after every row is written.
	delete_custom_fields({"Item": list(FIELDS)})
	frappe.db.delete("Variant Field", {"field_name": ("in", list(FIELDS))})
	if columns:
		frappe.db.drop_columns("Item", columns)
		# has_column reads a cached column list that MariaDB DDL leaves stale.
		frappe.client_cache.delete_value("table_columns::tabItem")
	if copied:
		from commera.search.build import enqueue_full_rebuild

		# Bulk inserts skip the hook that reindexes a saved translation.
		enqueue_full_rebuild(deduplicate=True)


def read_arabic_items(columns: list[str]) -> list[dict]:
	"""Each Item with an Arabic value: {"name", product field: value}. Blank values are left out."""
	if not columns:
		return []
	item = frappe.qb.DocType("Item")
	has_value = None
	for column in columns:
		condition = item[column].isnotnull() & (item[column] != "")
		has_value = condition if has_value is None else has_value | condition
	rows = frappe.qb.from_(item).select(item.name, *(item[column] for column in columns)).where(has_value)
	return [
		{"name": row.name}
		| {FIELDS[column]: value for column in columns if (value := cstr(row.get(column)).strip())}
		for row in rows.run(as_dict=True)
	]


def copy_batch(items: list[dict], columns: list[str]) -> int:
	"""Write the Arabic values of `items` onto every product of each Item. Returns the rows written."""
	by_item = {item["name"]: item for item in items}
	products = frappe.get_all(
		PRODUCT, filters={"item_style": ("in", list(by_item))}, fields=["name", "item_style", "display_name"]
	)
	if not products:
		return 0
	fields = [FIELDS[column] for column in columns]
	sources = get_sources(PRODUCT, products, fields)
	existing = read_existing([product.name for product in products], fields)
	timestamp = now()
	rows = [
		make_row(product.name, field, by_item[product.item_style][field], source[field], timestamp)
		for product, source in zip(products, sources, strict=True)
		for field in fields
		if field in by_item[product.item_style] and (product.name, field) not in existing
	]
	if rows:
		frappe.db.bulk_insert(DOCTYPE, ROW_FIELDS, rows, ignore_duplicates=True)
	return len(rows)


def read_existing(names: list[str], fields: list[str]) -> set[tuple[str, str]]:
	"""(product, field) of the shop-wide Arabic translations already written. The patch keeps them."""
	rows = frappe.get_all(
		DOCTYPE,
		filters={
			"reference_doctype": PRODUCT,
			"reference_name": ("in", names),
			"reference_field": ("in", fields),
			"language": LANGUAGE,
			"market": SHOP_WIDE,
		},
		fields=["reference_name", "reference_field"],
	)
	return {(row.reference_name, row.reference_field) for row in rows}


def make_row(product: str, field: str, value: str, source: str, timestamp: str) -> tuple:
	"""A Content Translation row as a save writes it: sanitised, current against the source now."""
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
		sanitize(value),
		get_source_hash(source),
	)


def sanitize(value: str) -> str:
	# Document._sanitize_content cleans only values that look like HTML.
	return sanitize_html(value) if "<" in value or ">" in value else value
