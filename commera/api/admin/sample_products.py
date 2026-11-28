# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from commera.api.admin.catalog import (
	create_collection,
	create_product,
	delete_product,
	ensure_attribute_exists,
	set_product_published,
)
from commera.install_fashion_demo_data import FASHION_PRODUCTS, IMAGE_ROOT
from commera.install_summer_demo import get_currency_profile, to_local_price
from commera.swatches import COLOUR_ATTRIBUTE
from commera.utils import get_store_currency

SAMPLE_FLAG = "custom_is_sample_product"
SAMPLE_COLLECTION = "Demo products"
SAMPLE_SIZES = ("S", "M", "L")

SAMPLE_PRODUCTS = (
	{"code": "KNIT-CARDIGAN", "options": ("Pink", "Purple")},
	{"code": "DENIM-OVERALL-SHORTS"},
	{"code": "PRINTED-SPREAD-SHIRT"},
	{"code": "MESH-LEGGINGS"},
)


@frappe.whitelist()
def get_sample_products():
	frappe.has_permission("Item", ptype="read", throw=True)
	return {"count": len(get_sample_product_names())}


@frappe.whitelist(methods=["POST"])
def load_sample_products():
	frappe.has_permission("Item", ptype="create", throw=True)
	if get_sample_product_names():
		frappe.throw(_("Demo products are already in your catalogue."))

	ensure_sample_collection()
	profile = get_price_profile()
	catalogue = {product["code"]: product for product in FASHION_PRODUCTS}

	created = []
	for sample in SAMPLE_PRODUCTS:
		product = catalogue[sample["code"]]
		if frappe.db.exists("Item", product["name"]):
			continue
		item_template = save_sample_product(product, sample.get("options"), profile)
		created.append({"item_template": item_template, "title": product["name"]})

	return {"created": created}


@frappe.whitelist(methods=["POST"])
def remove_sample_products():
	removed = []
	kept = []
	for item_template in get_sample_product_names():
		savepoint = f"sample_{frappe.generate_hash(length=10)}"
		try:
			frappe.db.savepoint(savepoint)
			delete_product(item_template)
		except frappe.ValidationError:
			frappe.db.rollback(save_point=savepoint)
			frappe.clear_last_message()
			kept.append(item_template)
		else:
			removed.append(item_template)

	if frappe.db.exists("Item Group", SAMPLE_COLLECTION):
		try:
			frappe.delete_doc("Item Group", SAMPLE_COLLECTION)
		except frappe.LinkExistsError:
			frappe.clear_last_message()

	return {"removed": removed, "kept": kept}


def get_sample_product_names():
	return frappe.get_all("Item", filters={SAMPLE_FLAG: 1, "has_variants": 1}, pluck="name")


def ensure_sample_collection():
	if not frappe.db.exists("Item Group", SAMPLE_COLLECTION):
		create_collection(SAMPLE_COLLECTION)


def get_price_profile():
	try:
		return get_currency_profile(get_store_currency())
	except frappe.ValidationError:
		frappe.clear_last_message()
		return {"price_multiplier": 1, "price_rounding": 1}


def save_sample_product(product, options, profile):
	option_sizes = [{"option": option, "sizes": list(SAMPLE_SIZES)} for option in options or ()]
	if option_sizes:
		ensure_attribute_exists(COLOUR_ATTRIBUTE, options[0], options[0][:3].upper())
	item_template = create_product(
		title=product["name"],
		collection=SAMPLE_COLLECTION,
		option_attribute=COLOUR_ATTRIBUTE if option_sizes else None,
		option_sizes=option_sizes,
		price=to_local_price(product["base_price"], profile),
		sale_price=to_local_price(product["sale_price"], profile),
	)["name"]
	frappe.db.set_value("Item", item_template, {"description": product["description"], SAMPLE_FLAG: 1})

	images_by_option = {variant["color"]: variant["images"] for variant in product["variants"]}
	configurator = frappe.db.get_value("Style Attribute Configurator", {"item_template": item_template})
	for variant in frappe.get_all(
		"Style Attribute Variant", filters={"configurator": configurator}, fields=["name", "attribute_value"]
	):
		images = images_by_option.get(variant.attribute_value) or product["variants"][0]["images"]
		style_variant = frappe.get_doc("Style Attribute Variant", variant.name)
		for image in images:
			style_variant.append("images", {"image": f"{IMAGE_ROOT}/{image}"})
		style_variant.save()

	set_product_published(item_template, 1)
	return item_template
