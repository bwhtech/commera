"""Page data for Builder theme pages (Builder's builder_page_data hook stores it under `commera`).
Builder binds keys, not expressions, so every value is display-ready: formatted prices, finished URLs."""

from urllib.parse import urlencode

import frappe

from commera.builder_themes.cards import CARD_IMAGE_WIDTH, get_cards
from commera.builder_themes.listing import Listing
from commera.builder_themes.pages import HOME, PRODUCT_DETAIL, PRODUCT_LISTING, get_page_role
from commera.localization.urls import url
from commera.sdk import catalog, shop
from commera.sdk.format import image_url, money, product_url

PRODUCT_IMAGE_WIDTH = 1280
THUMBNAIL_WIDTH = 320
HOME_PRODUCT_COUNT = 8
RELATED_PRODUCT_COUNT = 4


def get_page_data(page) -> dict:
	"""The builder_page_data hook: nothing for a page outside every Commera theme."""
	role = get_page_role(page.name)
	if not role:
		return {}
	return get_data_for(role.page_type, frappe.form_dict)


def get_data_for(page_type: str, form: dict) -> dict:
	builders = {HOME: get_home_data, PRODUCT_LISTING: get_listing_data, PRODUCT_DETAIL: get_product_data}
	return {**get_shop_data(), **builders[page_type](form)}


def get_shop_data() -> dict:
	store = shop.get_shop()
	return {
		"shop": {
			"name": store["name"],
			"description": store["description"],
			"logo": store["logo"],
			"home_url": url("/"),
			"products_url": url("/products"),
			"sale_url": url("/products?has_discount=1"),
			"search_url": url("/products"),
			"cart_url": url("/cart"),
			"account_url": url("/account/dashboard"),
		},
		"menu": [get_menu_link(item) for item in store["menu"]],
		"footer": store["footer"],
	}


def get_menu_link(item: dict) -> dict:
	return {
		"title": item["title"],
		"url": item["url"] or "",
		"items": [get_menu_link(child) for child in item["items"]],
	}


def get_home_data(form: dict) -> dict:
	newest = catalog.list_products(sort="new_arrival", page_size=HOME_PRODUCT_COUNT)
	on_sale = catalog.list_products(on_sale=True, page_size=RELATED_PRODUCT_COUNT)
	return {
		"featured_products": get_cards(newest["products"]),
		"sale_products": get_cards(on_sale["products"]),
		"collections": [get_collection_link(collection) for collection in catalog.list_collections()],
	}


def get_listing_data(form: dict) -> dict:
	return Listing(form).get_data()


def get_product_data(form: dict) -> dict:
	# The editor opens the page without a handle: it previews the newest product instead.
	handle = form.get("route") or get_sample_handle()
	product = catalog.get_product(handle) if handle else None
	if not product:
		raise frappe.PageDoesNotExistError
	return {
		"product": get_product_shape(product),
		"related_products": get_cards(catalog.get_recommendations(product["handle"], RELATED_PRODUCT_COUNT)),
	}


def get_sample_handle() -> str | None:
	products = catalog.list_products(sort="new_arrival", page_size=1)["products"]
	return products[0]["handle"] if products else None


def get_collection_link(collection: dict) -> dict:
	return {
		"title": collection["title"],
		"url": url(f"/products?{urlencode({'category': collection['handle']})}"),
		"image": image_url(collection["image"], CARD_IMAGE_WIDTH) or "",
	}


def get_product_shape(product: dict) -> dict:
	variants = product["variants"]
	currency = product["currency"]
	color_option = next(
		(option for option in product["options"] if any(value.get("handle") for value in option["values"])),
		None,
	)
	images = [
		{"url": image_url(path, PRODUCT_IMAGE_WIDTH), "thumbnail": image_url(path, THUMBNAIL_WIDTH)}
		for path in product["images"]
	]
	return {
		"title": product["title"],
		"vendor": product["vendor"] or "",
		"description_html": product["description_html"],
		"url": product_url(product["handle"]),
		"price": money(product["price"], currency),
		"is_available": product["available"],
		"image": images[0]["url"] if images else "",
		"images": images,
		"color": product["color"] or "",
		"color_label": color_option["name"] if color_option else "",
		"colors": [get_color_link(value) for value in color_option["values"]] if color_option else [],
		"has_sizes": len(variants) > 1,
		"sizes": [get_size(variant, currency) for variant in variants] if len(variants) > 1 else [],
		# A product sold in one size adds that size straight away.
		"default_variant_id": variants[0]["id"] if len(variants) == 1 else "",
		"collection": get_product_collection_link(product["collection"]),
		"rating": product["rating"]["average"],
		"review_count": product["rating"]["count"],
	}


def get_color_link(value: dict) -> dict:
	return {
		"name": value["name"],
		"url": product_url(value["handle"]),
		"is_selected": value["selected"],
		"is_available": value["available"],
		"swatch_color": (value.get("swatch") or {}).get("color") or "",
	}


def get_size(variant: dict, currency: str) -> dict:
	return {
		"name": variant["title"],
		"variant_id": variant["id"],
		"price": money(variant["price"], currency),
		"is_available": variant["available"],
	}


def get_product_collection_link(collection: dict | None) -> dict | None:
	if not collection:
		return None
	return {
		"title": collection["title"],
		"url": url(f"/products?{urlencode({'category': collection['handle']})}"),
	}
