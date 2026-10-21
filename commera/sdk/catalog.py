import frappe
from frappe import _
from frappe.utils import create_batch
from frappe.utils.data import cint, cstr, flt
from frappe.website.utils import cleanup_page_name

from commera.api.admin.catalog import (
	DEFAULT_OPTION_ATTRIBUTE,
	DEFAULT_SIZE_VALUE,
	get_default_rates,
	get_selling_rates,
)
from commera.api.admin.orders import get_reporting_currency
from commera.plugin_events import get_ecommerce_warehouse, get_listed_items
from commera.product_detail import get_product_detail
from commera.sdk.types import CatalogItem, Collection, Product, ProductCard, ProductOption, ProductPage
from commera.search.facets import get_product_filters
from commera.search.record_builder import rates_by_item_code, sizes_for_variants
from commera.swatches import get_swatch_map
from commera.utils import (
	IN_CLAUSE_CHUNK_SIZE,
	get_available_stocks,
	get_product_list,
	get_total_product_count,
)

__all__ = [
	"SORT_KEYS",
	"get_collection",
	"get_items",
	"get_product",
	"list_collections",
	"list_products",
]

SORT_KEYS = ("default", "price_low", "price_high", "name", "new_arrival", "discount")
MAX_PAGE_SIZE = 48


def get_items(item_codes: list[str]) -> dict[str, CatalogItem]:
	"""`price` is what a shopper pays, `list_price` the struck-through figure; both None until the store's
	price lists are set. A code that is not an Item is left out."""
	frappe.has_permission("Item", ptype="read", throw=True)
	items = {}
	for item_code_chunk in create_batch(
		list({cstr(item_code) for item_code in item_codes}), IN_CLAUSE_CHUNK_SIZE
	):
		items.update(read_items(item_code_chunk))
	return items


def read_items(item_codes: list[str]) -> dict[str, CatalogItem]:
	rows = frappe.get_all(
		"Item", filters={"name": ["in", item_codes]}, fields=["name", "item_name", "variant_of"]
	)
	found_codes = [row.name for row in rows]
	if not found_codes:
		return {}

	listed_items = get_listed_items(found_codes)
	prices, list_prices = get_store_prices(found_codes)
	warehouse = get_ecommerce_warehouse()
	# get_available_stocks reads a missing warehouse as one literally named "website_warehouse".
	stocks = get_available_stocks(found_codes, warehouse) if warehouse else {}
	currency = get_reporting_currency()

	return {
		row.name: {
			"item_code": row.name,
			"title": row.item_name,
			"product": row.variant_of or row.name,
			"is_listed": row.name in listed_items,
			"price": prices.get(row.name),
			"list_price": list_prices.get(row.name),
			"currency": currency,
			"available_qty": flt(stocks.get(row.name, {}).get("stock_qty")),
			"unlimited": bool(stocks.get(row.name, {}).get("unlimited")),
		}
		for row in rows
	}


def get_store_prices(item_codes: list[str]) -> tuple[dict, dict]:
	price_lists = frappe.get_cached_value(
		"Commera Settings", "Commera Settings", ["default_price_list", "sale_price_list"]
	)
	if not all(price_lists):
		return {}, {}
	return get_selling_rates(item_codes), get_default_rates(item_codes)


# Shopper reads: published products only, the same for every caller, so they need no permission.


def list_products(
	collection: str | None = None,
	query: str | None = None,
	brands: list[str] | None = None,
	colors: list[str] | None = None,
	sizes: list[str] | None = None,
	min_price: float | None = None,
	max_price: float | None = None,
	on_sale: bool = False,
	sort: str = "default",
	page: int = 1,
	page_size: int = 24,
) -> ProductPage:
	"""One page of published products, as the storefront grid lists them, with the facets of the whole
	result. `collection` is a collection handle; an unknown one raises DoesNotExistError."""
	if sort not in SORT_KEYS:
		frappe.throw(_("Sort must be one of {0}.").format(", ".join(SORT_KEYS)))
	page, page_size = max(cint(page), 1), min(max(cint(page_size), 1), MAX_PAGE_SIZE)
	filters = {
		"subcategory": [get_item_group(collection)] if collection else [],
		"search": cstr(query).strip(),
		"brands": list(brands or []),
		"colors": list(colors or []),
		"sizes": list(sizes or []),
		"has_discount": bool(on_sale),
		"category": "",
		**({"min_price": flt(min_price)} if min_price is not None else {}),
		**({"max_price": flt(max_price)} if max_price is not None else {}),
	}

	cards = get_product_list(filters=filters, page=page, page_length=page_size, sort_by=sort)
	facets, price_range = get_product_filters(filters)
	return {
		"products": get_product_cards(cards),
		"total": get_total_product_count(filters=filters),
		"page": page,
		"page_size": page_size,
		"facets": {
			"brands": facets.get("brands") or [],
			"colors": facets.get("colors") or [],
			"sizes": facets.get("sizes") or [],
			"price": {"min": flt(price_range.get("min_price")), "max": flt(price_range.get("max_price"))},
		},
	}


def get_product(handle: str) -> Product | None:
	"""A published product by its route, or None."""
	detail = get_product_detail(cstr(handle))
	if not detail:
		return None

	product_variant, item = detail["product_variant"], detail["product"]
	variants = get_variants(detail["available_sizes"])
	return {
		"id": product_variant.name,
		"handle": product_variant.route,
		"title": product_variant.display_name or item.item_name,
		"vendor": item.brand,
		"color": product_variant.attribute_value,
		"description_html": item.description or "",
		"images": detail["images"],
		"collection": get_product_collection(product_variant.item_group),
		"currency": get_store_currency(),
		"price": min((variant["price"] for variant in variants), default=0),
		"available": any(variant["available"] for variant in variants),
		"options": get_options(product_variant, detail["available_sizes"]),
		"variants": variants,
		"selected_variant_id": (detail["selected_item"] or {}).get("item_code"),
		"rating": {
			"average": flt(product_variant.average_rating),
			"count": cint(product_variant.review_count),
		},
		"seo": {
			"title": product_variant.meta_title or product_variant.display_name,
			"description": product_variant.meta_description or "",
			"noindex": bool(product_variant.noindex),
		},
		"updated_at": str(product_variant.modified),
	}


def list_collections() -> list[Collection]:
	"""Every Item Group that holds a published product."""
	rows = frappe.get_all(
		"Item Group",
		filters={"name": ("in", get_listed_item_groups() or [""])},
		fields=["name", "custom_displayname", "image", "modified"],
		order_by="custom_displayname asc",
	)
	return [get_collection_shape(row) for row in rows]


def get_collection(handle: str) -> Collection | None:
	item_group = find_item_group(handle)
	if not item_group:
		return None
	return get_collection_shape(
		frappe.db.get_value(
			"Item Group", item_group, ["name", "custom_displayname", "image", "modified"], as_dict=True
		)
	)


def get_collection_handle(item_group: str) -> str:
	return cleanup_page_name(item_group).replace("_", "-")


def get_item_group(handle: str) -> str:
	if item_group := find_item_group(handle):
		return item_group
	raise frappe.DoesNotExistError(_("Collection {0} not found").format(handle))


def find_item_group(handle: str) -> str | None:
	return next((group for group in get_listed_item_groups() if get_collection_handle(group) == handle), None)


def get_listed_item_groups() -> list[str]:
	return frappe.get_all(
		"Style Attribute Variant",
		filters={"is_published": 1, "item_group": ("is", "set")},
		pluck="item_group",
		distinct=True,
	)


def get_collection_shape(row) -> Collection:
	return {
		"handle": get_collection_handle(row.name),
		"title": row.custom_displayname or row.name,
		"image": row.image,
		"updated_at": str(row.modified),
	}


def get_store_currency() -> str:
	"""The currency of the sale price list, which every shopper price is read from."""
	return frappe.get_cached_value(
		"Price List", frappe.get_cached_doc("Commera Settings").get_sale_price_list(), "currency"
	)


def get_product_cards(cards: list[dict]) -> list[ProductCard]:
	item_codes = [size["item_code"] for card in cards for size in card["sizes"]]
	stock = get_available_stocks(item_codes, get_ecommerce_warehouse())
	currency = get_store_currency()
	return [get_product_card(card, stock, currency) for card in cards]


def get_product_card(card: dict, stock: dict, currency: str) -> ProductCard:
	return {
		"id": card["name"],
		"handle": card["route"],
		"title": card["display_name"] or card["item_name"],
		"vendor": card["brand"],
		"color": card["attribute_value"],
		"image": card["image"],
		"hover_image": card["hover_image"],
		"currency": currency,
		"price": flt(card["effective_price"]),
		"compare_at_price": flt(card["default_price"]) if cint(card["has_discount"]) else None,
		"available": any(stock.get(size["item_code"], {}).get("in_stock") for size in card["sizes"]),
		"rating": {"average": flt(card["average_rating"]), "count": cint(card["review_count"])},
		"updated_at": card["modified"],
	}


def get_variants(sizes: list[dict]) -> list[dict]:
	settings = frappe.get_cached_doc("Commera Settings")
	default_rate, sale_rate, _sale_ends = rates_by_item_code(
		[size["item_code"] for size in sizes], settings.default_price_list, settings.sale_price_list
	)
	return [
		get_variant(size, default_rate.get(size["item_code"]), sale_rate.get(size["item_code"]))
		for size in sizes
	]


def get_variant(size: dict, default_price: float | None, sale_price: float | None) -> dict:
	price = flt(sale_price if sale_price is not None else default_price)
	stock = size["stock_detail"]
	return {
		"id": size["item_code"],
		"title": size["size"],
		"price": price,
		"compare_at_price": flt(default_price) if default_price and price < flt(default_price) else None,
		"available": bool(stock.get("in_stock")),
		"quantity_available": None if stock.get("unlimited") else flt(stock.get("stock_qty")),
	}


def get_options(product_variant, sizes: list[dict]) -> list[ProductOption]:
	"""The colour axis links sibling products; the size axis picks a variant. Fallback axes stay hidden."""
	options = []
	attribute = frappe.db.get_value(
		"Style Attribute Configurator", product_variant.configurator, "item_attribute"
	)
	if attribute and attribute != DEFAULT_OPTION_ATTRIBUTE:
		options.append({"name": attribute, "values": get_sibling_values(product_variant)})
	if len(sizes) > 1 or (sizes and sizes[0]["size"] != DEFAULT_SIZE_VALUE):
		options.append({"name": _("Size"), "values": [{"name": size["size"]} for size in sizes]})
	return options


def get_sibling_values(product_variant) -> list[dict]:
	siblings = frappe.get_all(
		"Style Attribute Variant",
		filters={"configurator": product_variant.configurator, "is_published": 1},
		fields=["name", "route", "attribute_value"],
		order_by="idx asc, attribute_value asc",
	)
	sizes_by_variant = sizes_for_variants([sibling.name for sibling in siblings])
	item_codes = [size["item_code"] for sizes in sizes_by_variant.values() for size in sizes]
	stock = get_available_stocks(item_codes, get_ecommerce_warehouse())
	swatches = get_swatch_map()
	return [
		{
			"name": sibling.attribute_value,
			"handle": sibling.route,
			"selected": sibling.name == product_variant.name,
			"available": any(
				stock.get(size["item_code"], {}).get("in_stock")
				for size in sizes_by_variant.get(sibling.name, [])
			),
			"swatch": swatches.get(sibling.attribute_value),
		}
		for sibling in siblings
	]


def get_product_collection(item_group: str | None) -> dict | None:
	if not item_group:
		return None
	title = frappe.get_cached_value("Item Group", item_group, "custom_displayname")
	return {"handle": get_collection_handle(item_group), "title": title or item_group}
