import frappe
from frappe import _
from frappe.utils.data import get_datetime

from commera import seo
from commera.api.admin.catalog import DEFAULT_OPTION_ATTRIBUTE, DEFAULT_SIZE_VALUE
from commera.api.reviews import PAGE_LENGTH as REVIEWS_PAGE_LENGTH
from commera.api.reviews import get_reviews
from commera.localization import url
from commera.product_detail import get_product_detail
from commera.utils import get_available_stock, get_product_list


def get_context(context):
	product_route = frappe.form_dict.get("route")
	size_selected = frappe.form_dict.get("size")

	detail = get_product_detail(product_route, size_selected)
	if not detail:
		raise frappe.PageDoesNotExistError()

	product_variant = detail["product_variant"]
	product = detail["product"]
	selected_item = detail["selected_item"]

	context.product_variant = product_variant
	context.product = product
	context.images = detail["images"]
	context.product_in_stock = detail["in_stock"]

	add_selected_item_fields(selected_item)
	content = add_product_content(context, product_variant, product)

	resolved_size = selected_item["size"] if selected_item else None
	context.available_sizes = detail["available_sizes"]
	context.selected_size = resolved_size
	context.size_selected = resolved_size
	context.selected_item = selected_item
	context.selected_price = detail["selected_price"]
	context.default_price = detail["default_price"]
	# A product created with no options hangs on the fallback axis, and a sizeless one on the fallback
	# size. Naming either on the page would read as "Standard: Standard" or "Available in 1 sizes".
	context.show_option_axis = (
		frappe.db.get_value("Style Attribute Configurator", product_variant.configurator, "item_attribute")
		!= DEFAULT_OPTION_ATTRIBUTE
	)
	context.show_sizes = len(detail["available_sizes"]) > 1 or detail["selected_size"] != DEFAULT_SIZE_VALUE
	context.recommended_items = get_recommended_products(product_variant)
	context.other_variants = get_other_variants(product_variant)
	context.discount_percent = detail["discount_percent"]
	context.size_chart = get_size_chart(product.brand, product_variant.item_group)
	context.item_qty = get_available_stock(product.item_code, detail["warehouse"])
	context.reviews = get_reviews_for_context(product_variant.name)
	# Labels in the page language: the templates and the breadcrumb JSON-LD print them as they are.
	context.breadcrumbs = [
		{"label": _("Products"), "href": url("/products/")},
		{"label": context.product_title, "href": ""},
	]

	add_seo(context, detail, content)


def add_selected_item_fields(selected_item):
	"""The size's own fields, and its cart line title in the request language."""
	# sdk.catalog imports this module, so the SDK is imported where it is used.
	from commera.sdk.lines import LineProducts

	item = frappe.get_cached_doc("Item", selected_item["item_code"])
	selected_item.update(
		{
			"item_name": item.item_name,
			"title": LineProducts([item.name]).get_title(item.name, item.item_name),
			"style_code": item.get("custom_style_code", ""),
			"material": item.get("custom_material", ""),
			"description": item.get("description", ""),
		}
	)


def add_product_content(context, product_variant, item):
	"""The title and description in the request language, as the SDK's product page has them."""
	from commera.sdk.catalog import get_product_content

	content = get_product_content(product_variant, item)
	context.product_title = content["display_name"] or item.item_name
	context.product_description = content["description"]
	# Item saves default a blank description to the Item's code or name.
	context.show_product_description = bool(content["description"]) and content["description"] not in (
		item.name,
		item.item_name,
	)
	return content


def add_seo(context, detail, content):
	"""Meta tags and JSON-LD from the translated content the page shows, on copies of the records."""
	product_variant = {
		**detail["product_variant"].as_dict(),
		"display_name": context.product_title,
		"meta_title": content["meta_title"],
		"meta_description": content["meta_description"],
	}
	product = {**detail["product"].as_dict(), "description": content["description"]}
	price = detail["selected_price"]
	availability = "InStock" if detail["in_stock"] else "OutOfStock"

	context.seo = seo.build_product_seo(
		product_variant,
		product,
		image_url=seo.get_product_og_image(product_variant["route"]),
		price=price,
		availability=availability,
	)
	context.json_ld = [
		seo.build_product_json_ld(
			product_variant,
			product,
			images=detail["images"],
			price=price,
			availability=availability,
			review_count=context.reviews["review_count"],
			average_rating=context.reviews["average_rating"],
		),
		seo.build_breadcrumb_json_ld(context.breadcrumbs),
	]


def get_recommended_products(product_variant, limit=8):
	style_attribute_variants = frappe.get_all(
		"Style Attribute Variant",
		filters={
			"item_group": product_variant.item_group,
			"is_published": True,
			"configurator": ["not in", [product_variant.configurator]],
		},
		pluck="name",
		limit=limit,
	)
	if not style_attribute_variants:
		return []
	return get_product_list(product_list=style_attribute_variants)


def get_other_variants(product_variant):
	variants = frappe.get_all(
		"Style Attribute Variant",
		filters={
			"configurator": product_variant.configurator,
			"name": ("!=", product_variant.name),
			"is_published": True,
		},
		pluck="name",
	)
	if not variants:
		return []
	return get_product_list(product_list=variants)


def get_reviews_for_context(variant):
	"""Jinja's `| tojson` uses stdlib json.dumps, which can't serialise the raw datetime objects
	get_reviews() returns, so isoformat them here before they reach the template."""
	reviews = get_reviews(variant, page_length=REVIEWS_PAGE_LENGTH)
	for review in reviews["reviews"]:
		review["creation"] = get_datetime(review["creation"]).isoformat()
		if review["replied_on"]:
			review["replied_on"] = get_datetime(review["replied_on"]).isoformat()
	return reviews


def get_size_chart(brand, item_group):
	return frappe.get_cached_value(
		"Size Chart", {"brand": brand, "item_group": item_group}, "size_chart_json"
	)
