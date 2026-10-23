import frappe
from frappe import _
from frappe.utils import create_batch
from frappe.utils.caching import redis_cache
from frappe.utils.data import cint, cstr, flt, sha256_hash

from commera.api.admin.catalog import (
	DEFAULT_OPTION_ATTRIBUTE,
	DEFAULT_SIZE_VALUE,
	get_default_rates,
	get_selling_rates,
)
from commera.plugin_events import get_ecommerce_warehouse, get_listed_items
from commera.product_detail import get_product_detail
from commera.sdk.types import (
	CartLineProduct,
	CatalogItem,
	Collection,
	FacetValue,
	Product,
	ProductCard,
	ProductOption,
	ProductPage,
)
from commera.search.facets import get_listing_facet_counts, get_price_range
from commera.search.record_builder import images_for_variants, rates_by_item_code, sizes_for_variants
from commera.shop_data import get_storefront_menu
from commera.swatches import get_swatch_map
from commera.utils import (
	IN_CLAUSE_CHUNK_SIZE,
	get_available_stocks,
	get_product_list,
	get_store_currency,
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
FACETS_CACHE_PREFIX = "commera:storefront_facets:"
FACETS_CACHE_SECONDS = 5 * 60
# Only a top-level menu entry owns a route_slug, so these are the menu tabs.
COLLECTION_FILTERS = {"enabled": 1, "route_slug": ("is", "set")}
COLLECTION_FIELDS = ["route_slug", "display_name", "category_name", "image", "modified"]


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
	currency = get_store_currency()

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
		"subcategory": [],
		"search": cstr(query).strip(),
		"brands": list(brands or []),
		"colors": list(colors or []),
		"sizes": list(sizes or []),
		"has_discount": bool(on_sale),
		"category": "",
		**(get_collection_filters(collection) if collection else {}),
		**({"min_price": flt(min_price)} if min_price is not None else {}),
		**({"max_price": flt(max_price)} if max_price is not None else {}),
	}

	cards = get_product_list(filters=filters, page=page, page_length=page_size, sort_by=sort)
	return {
		"products": get_product_cards(cards),
		"total": get_total_product_count(filters=filters),
		"page": page,
		"page_size": page_size,
		"facets": {**get_facets(filters), "price": get_price_facet()},
	}


def get_facets(filters: dict) -> dict[str, list[FacetValue]]:
	cache_key = f"{FACETS_CACHE_PREFIX}{sha256_hash(frappe.as_json(filters))}"
	facets = frappe.cache.get_value(cache_key)
	if facets is None:
		facets = {key: get_facet_values(counts) for key, counts in get_listing_facet_counts(filters).items()}
		frappe.cache.set_value(cache_key, facets, expires_in_sec=FACETS_CACHE_SECONDS)
	return facets


@redis_cache(ttl=FACETS_CACHE_SECONDS)
def get_price_facet() -> dict:
	price_range = get_price_range()
	return {"min": flt(price_range.get("min_price")), "max": flt(price_range.get("max_price"))}


def get_facet_values(counts: dict[str, int]) -> list[FacetValue]:
	return [{"value": value, "count": count} for value, count in counts.items()]


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
	"""Every enabled menu tab, the Ecommerce Categories `/products?category=` lists."""
	rows = frappe.get_all(
		"Ecommerce Category",
		filters=COLLECTION_FILTERS,
		fields=COLLECTION_FIELDS,
		order_by="display_order asc, category_name asc",
	)
	return [get_collection_shape(row) for row in rows]


def get_collection(handle: str) -> Collection | None:
	rows = frappe.get_all(
		"Ecommerce Category",
		filters={**COLLECTION_FILTERS, "route_slug": cstr(handle)},
		fields=COLLECTION_FIELDS,
		limit=1,
	)
	return get_collection_shape(rows[0]) if rows else None


def get_collection_filters(handle: str) -> dict:
	"""The listing filters of the menu tab's own link, as its `/products?category=` href carries them."""
	root = next((node for node in get_storefront_menu() if node["route_slug"] == handle), None)
	if not root:
		raise frappe.DoesNotExistError(_("Collection {0} not found").format(handle))
	return {"category": root["route_slug"], "subcategory": root["item_groups"]}


def get_collection_shape(row) -> Collection:
	return {
		"handle": row.route_slug,
		"title": row.display_name or row.category_name,
		"image": row.image,
		"updated_at": str(row.modified),
	}


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
	"""The menu tab whose entries link the product's item group."""
	if not item_group:
		return None
	root = next(
		(root for root in get_storefront_menu() if root["route_slug"] and links_item_group(root, item_group)),
		None,
	)
	return {"handle": root["route_slug"], "title": root["label"]} if root else None


def links_item_group(node: dict, item_group: str) -> bool:
	return item_group in node["item_groups"] or any(
		links_item_group(child, item_group) for child in node["children"]
	)


def get_line_products(item_codes: list[str]) -> dict[str, CartLineProduct]:
	"""The published product, size and image that sell each item."""
	rows = frappe.get_all(
		"Color Size Item",
		filters={"item_code": ("in", item_codes or [""]), "parenttype": "Style Attribute Variant"},
		fields=["item_code", "size", "parent"],
	)
	variants = {
		row.name: row
		for row in frappe.get_all(
			"Style Attribute Variant",
			filters={"name": ("in", [row.parent for row in rows] or [""]), "is_published": 1},
			fields=["name", "route", "display_name"],
		)
	}
	images = images_for_variants(list(variants))
	return {
		row.item_code: {
			"handle": variants[row.parent].route,
			"title": variants[row.parent].display_name,
			"variant_title": row.size,
			"image": images.get(row.parent, {}).get("image"),
		}
		for row in rows
		if row.parent in variants
	}
