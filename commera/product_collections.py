"""A product's Product Collection rows own its collections. Item.item_group mirrors the first row,
because ERPNext requires it and breadcrumbs, size charts and page item_group read it."""

import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.utils import create_batch
from frappe.utils.nestedset import get_root_of

from commera.utils import IN_CLAUSE_CHUNK_SIZE

PRODUCT_COLLECTION = "Product Collection"
COLLECTIONS_FIELD = "custom_collections"
STORE_COLLECTIONS = "Store Collections"
ERPNEXT_ITEM_GROUPS = ("Products", "Raw Material", "Services", "Sub Assemblies", "Consumable")


def sync_collections(doc, method=None):
	"""Item validate: dedupe the rows, check new ones, and keep item_group equal to the first."""
	if not doc.meta.has_field(COLLECTIONS_FIELD):
		return
	if not doc.has_variants and not frappe.db.exists(
		"Style Attribute Configurator", {"item_template": doc.name}
	):
		return

	collections = [row.item_group for row in doc.get(COLLECTIONS_FIELD)]
	# A direct item_group edit (desk, ERPNext, an import) makes that group the primary.
	if doc.item_group and doc.has_value_changed("item_group"):
		collections.insert(0, doc.item_group)
	collections = list(dict.fromkeys(collection for collection in collections if collection))
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


def add_store_collections_parent() -> str:
	if not frappe.db.exists("Item Group", STORE_COLLECTIONS):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": STORE_COLLECTIONS,
				"parent_item_group": get_root_of("Item Group"),
				"is_group": 1,
			}
		).insert(ignore_permissions=True)
	return STORE_COLLECTIONS


def add_to_store_collections(item_groups):
	"""Move each group's top branch under Store Collections. ERPNext's own groups stay where they are."""
	parent = add_store_collections_parent()
	for name in get_branches_outside_store_collections(item_groups):
		branch = frappe.get_doc("Item Group", name)
		branch.parent_item_group = parent
		branch.save()


def get_branches_outside_store_collections(item_groups) -> list[str]:
	parent_by_group = dict(frappe.get_all("Item Group", fields=["name", "parent_item_group"], as_list=True))
	# The setup wizard names its groups in the site language.
	fixed = {get_root_of("Item Group"), STORE_COLLECTIONS, *ERPNEXT_ITEM_GROUPS}
	fixed.update(_(name) for name in ERPNEXT_ITEM_GROUPS)

	branches = []
	for item_group in dict.fromkeys(item_groups):
		if item_group not in parent_by_group or item_group in fixed:
			continue
		branch, parent = item_group, parent_by_group[item_group]
		while parent not in fixed and parent in parent_by_group:
			branch, parent = parent, parent_by_group[parent]
		if parent != STORE_COLLECTIONS and branch not in branches:
			branches.append(branch)
	return branches
