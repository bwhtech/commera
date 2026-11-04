import frappe
from frappe.utils import now

from commera.product_collections import COLLECTIONS_FIELD, PRODUCT_COLLECTION
from commera.search.build import enqueue_full_rebuild

FIELDS = [
	"name",
	"creation",
	"modified",
	"owner",
	"modified_by",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
	"item_group",
]


def execute():
	"""Give every product a first Product Collection row from its item_group, which stays the primary."""
	timestamp = now()
	values = [
		(
			frappe.generate_hash(length=10),
			timestamp,
			timestamp,
			"Administrator",
			"Administrator",
			1,
			item.name,
			COLLECTIONS_FIELD,
			"Item",
			item.item_group,
		)
		for item in get_products_without_rows()
	]
	if not values:
		return

	frappe.db.bulk_insert(
		PRODUCT_COLLECTION,
		fields=FIELDS,
		values=values,
	)
	# The search index files a page under its product's collections now, so it needs them.
	enqueue_full_rebuild(deduplicate=True)


def get_products_without_rows():
	item = frappe.qb.DocType("Item")
	row = frappe.qb.DocType(PRODUCT_COLLECTION)
	has_rows = (
		frappe.qb.from_(row)
		.select(row.parent)
		.where((row.parenttype == "Item") & (row.parentfield == COLLECTIONS_FIELD))
	)
	return (
		frappe.qb.from_(item)
		.select(item.name, item.item_group)
		.where((item.has_variants == 1) & item.item_group.notnull() & (item.item_group != ""))
		.where(item.name.notin(has_rows))
	).run(as_dict=True)
