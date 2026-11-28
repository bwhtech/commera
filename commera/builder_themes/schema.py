"""The shape of a theme page's data: the keys a block can bind, by page type.

A value is None (text, number or flag), a dict (an object with its own keys) or a one-item
list (a list to repeat, with the shape of each item). A test holds this to what page_data.py returns.
"""

from commera.builder_themes.pages import HOME, PRODUCT_DETAIL, PRODUCT_LISTING

# Every key sits under this one in Builder's page data.
ROOT_KEY = "commera"


def fields(*names: str) -> dict:
	return dict.fromkeys(names)


CARD = fields(
	"title",
	"url",
	"image",
	"hover_image",
	"vendor",
	"color",
	"price",
	"compare_at_price",
	"is_on_sale",
	"is_available",
	"rating",
	"review_count",
)

# A menu link holds menu links.
MENU_LINK = fields("title", "url")
MENU_LINK["items"] = [MENU_LINK]

SHARED = {
	"shop": fields(
		"name",
		"description",
		"logo",
		"home_url",
		"products_url",
		"sale_url",
		"search_url",
		"cart_url",
		"account_url",
	),
	"menu": [MENU_LINK],
	"footer": [{"title": None, "links": [fields("title", "url")]}],
}

PAGE_KEYS = {
	HOME: {
		"featured_products": [CARD],
		"sale_products": [CARD],
		"collections": [fields("title", "url", "image")],
	},
	PRODUCT_LISTING: {
		"title": None,
		"query": None,
		"total": None,
		"products": [CARD],
		"collections": [fields("title", "url", "is_active")],
		"filters": [{"name": None, "values": [fields("label", "count", "url", "is_active")]}],
		"active_filters": [fields("label", "url")],
		"has_active_filters": None,
		"clear_filters_url": None,
		"sort_options": [fields("label", "url", "is_active")],
		"pagination": {
			**fields("page", "last_page", "has_previous", "previous_url", "has_next", "next_url"),
			"pages": [fields("number", "url", "is_current")],
		},
	},
	PRODUCT_DETAIL: {
		"product": {
			**fields(
				"title",
				"vendor",
				"description_html",
				"url",
				"price",
				"is_available",
				"image",
				"color",
				"color_label",
				"has_sizes",
				"default_variant_id",
				"rating",
				"review_count",
			),
			"images": [fields("url", "thumbnail")],
			"colors": [fields("name", "url", "is_selected", "is_available", "swatch_color")],
			"sizes": [fields("name", "variant_id", "price", "is_available")],
			"collection": fields("title", "url"),
		},
		"related_products": [CARD],
	},
}


def get_page_schema(page_type: str) -> dict:
	"""What a block at the top of the page can bind: everything under `commera`."""
	return {ROOT_KEY: {**SHARED, **PAGE_KEYS[page_type]}}


def resolve(shape, key: str):
	"""The shape at a dotted key, or MISSING. A list is a leaf here: its items are bound inside a repeater."""
	for part in key.split("."):
		if not isinstance(shape, dict) or part not in shape:
			return MISSING
		shape = shape[part]
	return shape


def list_keys(shape: dict, prefix: str = "") -> list[str]:
	"""Every key a block can bind in this shape, dotted."""
	keys = []
	for name, value in shape.items():
		keys.append(prefix + name)
		if isinstance(value, dict):
			keys.extend(list_keys(value, f"{prefix}{name}."))
	return keys


MISSING = object()
