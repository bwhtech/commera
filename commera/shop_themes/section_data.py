from contextlib import contextmanager

import frappe
from markupsafe import Markup

from commera.utils import get_product_list

BLOCK_PRODUCTS_LOCAL_KEY = "commera_block_products"


@contextmanager
def block_products_cache():
	previous = getattr(frappe.local, BLOCK_PRODUCTS_LOCAL_KEY, None)
	setattr(frappe.local, BLOCK_PRODUCTS_LOCAL_KEY, {})
	try:
		yield
	finally:
		setattr(frappe.local, BLOCK_PRODUCTS_LOCAL_KEY, previous)


def get_block_products(blocks, setting_id="product"):
	product_names = [get_raw_setting_value(block.settings.get(setting_id)) for block in blocks]
	cards_by_name = get_product_cards(list(dict.fromkeys(name for name in product_names if name)))
	products_by_block = {
		block.id: cards_by_name[name]
		for block, name in zip(blocks, product_names, strict=True)
		if cards_by_name.get(name)
	}
	return list(products_by_block.values()), products_by_block


def get_product_cards(names):
	cache = getattr(frappe.local, BLOCK_PRODUCTS_LOCAL_KEY, None)
	if cache is None:
		cache = {}
	missing = [name for name in names if name not in cache]
	if missing:
		cards = get_product_list(product_list=missing, page_length=len(missing))
		cache.update(dict.fromkeys(missing))
		cache.update({card["name"]: card for card in cards})
	return {name: cache[name] for name in names}


def get_raw_setting_value(value):
	if isinstance(value, Markup):
		return value.unescape()
	return str(value or "")


def get_section_products(section):
	products, products_by_block = get_block_products(section.blocks)
	return {"products": products, "products_by_block": products_by_block}


def get_fallback_products(products):
	blocks = [
		frappe._dict(
			id=f"fallback-{index}", type="pick", index=index, settings=frappe._dict(), editor_attributes=""
		)
		for index in range(1, len(products) + 1)
	]
	return {
		"products": products,
		"products_by_block": {block.id: product for block, product in zip(blocks, products, strict=True)},
		"fallback_blocks": blocks,
	}
