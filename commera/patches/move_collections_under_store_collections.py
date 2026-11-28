import frappe

from commera.product_collections import COLLECTIONS_FIELD, PRODUCT_COLLECTION, add_to_store_collections


def execute():
	"""File the groups that hold store products under Store Collections, so the dashboard lists only them."""
	add_to_store_collections(get_product_item_groups())


def get_product_item_groups() -> list[str]:
	variant = frappe.qb.DocType("Style Attribute Variant")
	row = frappe.qb.DocType(PRODUCT_COLLECTION)
	configurator = frappe.qb.DocType("Style Attribute Configurator")
	variant_groups = (
		frappe.qb.from_(variant).select(variant.item_group).distinct().where(variant.item_group.notnull())
	).run(pluck=True)
	product_groups = (
		frappe.qb.from_(row)
		.join(configurator)
		.on(configurator.item_template == row.parent)
		.select(row.item_group)
		.distinct()
		.where((row.parenttype == "Item") & (row.parentfield == COLLECTIONS_FIELD))
	).run(pluck=True)
	return [item_group for item_group in dict.fromkeys([*variant_groups, *product_groups]) if item_group]
