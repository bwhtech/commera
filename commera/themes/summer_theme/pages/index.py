import frappe

from commera.utils import get_product_list
from commera.www import index

PICKS_FIELDS = ("best_picks", "deal_picks", "featured_picks")


def get_context(context):
	index.get_context(context)
	settings = frappe.get_cached_doc("Summer Theme Settings")
	context.picked_products = {field: get_picked_products(settings.get(field)) for field in PICKS_FIELDS}
	return context


def get_picked_products(rows):
	variants = [row.item_variant for row in rows]
	if not variants:
		return []

	return get_product_list(product_list=variants, page_length=len(variants))
