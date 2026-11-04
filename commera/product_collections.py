"""A product (Item template) sits in one or more collections: its Product Collection rows.

The rows are the one owner. Item.item_group stays as the primary collection, the first row, because
ERPNext requires it and breadcrumbs, size charts and Style Attribute Variant.item_group read it.
"""

import frappe
from frappe.query_builder import DocType
from frappe.utils import create_batch

from commera.utils import IN_CLAUSE_CHUNK_SIZE

PRODUCT_COLLECTION = "Product Collection"
COLLECTIONS_FIELD = "custom_collections"


def sync_collections(doc, method=None):
	"""Item validate: dedupe the rows, check new ones, and keep item_group equal to the first."""
	if not doc.has_variants or not doc.meta.has_field(COLLECTIONS_FIELD):
		return

	collections = [row.item_group for row in doc.get(COLLECTIONS_FIELD)]
	# A direct item_group edit (desk, ERPNext, an import) makes that group the primary.
	if doc.item_group and doc.has_value_changed("item_group"):
		collections.insert(0, doc.item_group)
	collections = list(dict.fromkeys(filter(None, collections)))
	if not collections:
		return

	check_new_collections(doc, collections)
	if collections != [row.item_group for row in doc.get(COLLECTIONS_FIELD)]:
		doc.set(COLLECTIONS_FIELD, [{"item_group": collection} for collection in collections])
	# A reordered row keeps its old idx, and idx is the order every reader loads rows in.
	for idx, row in enumerate(doc.get(COLLECTIONS_FIELD), start=1):
		row.idx = idx
	doc.item_group = collections[0]


def check_new_collections(doc, collections):
	"""Only what this save adds must be a leaf: an older product may sit in a parent group."""
	from commera.api.admin.catalog import get_collection

	previous = doc.get_doc_before_save()
	known = set()
	if previous:
		known = {previous.item_group, *(row.item_group for row in previous.get(COLLECTIONS_FIELD))}
	for collection in collections:
		if collection not in known:
			get_collection(collection)


def set_collections(item, collections):
	"""Give a product exactly these collections, the first being the primary."""
	item.set(COLLECTIONS_FIELD, [{"item_group": collection} for collection in collections])
	item.item_group = collections[0]


def get_product_collections(item_templates) -> dict[str, list[str]]:
	"""Each product's collections in order, primary first."""
	collections = {}
	for chunk in create_batch(list(item_templates), IN_CLAUSE_CHUNK_SIZE):
		for row in frappe.get_all(
			PRODUCT_COLLECTION,
			filters={"parenttype": "Item", "parentfield": COLLECTIONS_FIELD, "parent": ("in", chunk)},
			fields=["parent", "item_group"],
			order_by="idx asc",
		):
			collections.setdefault(row.parent, []).append(row.item_group)
	return collections


def get_item_collections(item_code) -> tuple[str, ...]:
	"""Every collection an Item (template or size) sits in. A size inherits its template's."""
	item = frappe.get_cached_value("Item", item_code, ["item_group", "variant_of"], as_dict=True)
	if not item:
		return ()
	template = item.variant_of or item_code
	return tuple(dict.fromkeys([item.item_group, *get_product_collections([template]).get(template, [])]))


def products_in(collections):
	"""Subquery: the products with a row in any of `collections`."""
	row = DocType(PRODUCT_COLLECTION)
	return (
		frappe.qb.from_(row)
		.select(row.parent)
		.where((row.parenttype == "Item") & (row.parentfield == COLLECTIONS_FIELD))
		.where(row.item_group.isin(collections))
	)


def variant_in_collections(variant, collections):
	"""Criterion: a Style Attribute Variant page whose product sits in any of `collections`."""
	# The page's own item_group still counts: the Item Group Map can file a page apart from its product.
	return variant.item_group.isin(collections) | variant.item_style.isin(products_in(collections))
