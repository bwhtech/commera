import frappe
from frappe import _
from frappe.utils import create_batch
from frappe.utils.caching import redis_cache
from frappe.utils.data import cint, cstr, flt, sha256_hash

from commera.api.admin.catalog import DEFAULT_OPTION_ATTRIBUTE, DEFAULT_SIZE_VALUE
from commera.api.variant_pricing import get_base_price_rows_by_key
from commera.localization import get_localization, translate
from commera.localization.market_prices import MarketPrices
from commera.plugin_events import get_ecommerce_warehouse, get_listed_items
from commera.product_detail import get_product_detail
from commera.sdk.types import (
	CatalogItem,
	Collection,
	FacetValue,
	PriceFacet,
	Product,
	ProductCard,
	ProductOption,
	ProductPage,
	SearchResults,
	Typeahead,
)
from commera.search.facets import get_listing_facet_counts, get_price_range
from commera.search.record_builder import rates_by_item_code, sizes_for_variants
from commera.search.typeahead import get_typeahead as get_search_typeahead
from commera.shop_data import get_storefront_menu, translate_categories
from commera.swatches import get_swatch_map
from commera.utils import (
	IN_CLAUSE_CHUNK_SIZE,
	get_available_stocks,
	get_product_list,
	get_total_product_count,
)
from commera.www.products.details import get_recommended_products

__all__ = [
	"SORT_KEYS",
	"get_collection",
	"get_items",
	"get_product",
	"get_product_cards_for",
	"get_recommendations",
	"get_typeahead",
	"list_brands",
	"list_collections",
	"list_products",
	"search",
]

SORT_KEYS = ("default", "price_low", "price_high", "name", "new_arrival", "discount")
MAX_PAGE_SIZE = 48
FACETS_CACHE_PREFIX = "commera:storefront_facets:"
FACETS_CACHE_SECONDS = 5 * 60
PRODUCT_DOCTYPE = "Style Attribute Variant"
PRODUCT_CONTENT_FIELDS = ("display_name", "description", "meta_title", "meta_description")
# Only a top-level menu entry owns a route_slug, so these are the menu tabs.
COLLECTION_FILTERS = {"enabled": 1, "route_slug": ("is", "set")}
COLLECTION_FIELDS = [
	"name",
	"route_slug",
	"display_name",
	"category_name",
	"image",
	"description",
	"meta_title",
	"meta_description",
	"noindex",
	"modified",
]


def get_items(item_codes: list[str]) -> dict[str, CatalogItem]:
	"""`price` is what a shopper pays in the request's market, `list_price` the compare-at figure.
	`price` is None for an item the market does not sell. A code that is not an Item is left out."""
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
	prices = MarketPrices.current()
	sale_rates, compare_at_rates = get_base_rates(prices, found_codes)
	warehouse = get_ecommerce_warehouse()
	# get_available_stocks reads a missing warehouse as one literally named "website_warehouse".
	stocks = get_available_stocks(found_codes, warehouse) if warehouse else {}

	return {
		row.name: {
			"item_code": row.name,
			"title": row.item_name,
			"product": row.variant_of or row.name,
			"is_listed": row.name in listed_items,
			"price": get_item_price(prices, sale_rates.get(row.name), compare_at_rates.get(row.name)),
			"list_price": compare_at_rates.get(row.name),
			"currency": prices.currency,
			"available_qty": flt(stocks.get(row.name, {}).get("stock_qty")),
			"unlimited": bool(stocks.get(row.name, {}).get("unlimited")),
		}
		for row in rows
	}


def get_base_rates(prices: MarketPrices, item_codes: list[str]) -> tuple[dict, dict]:
	"""(sale, compare-at) base rates by item code. Customer rows are negotiated contracts."""
	price_lists = [prices.sale_price_list, prices.compare_at_price_list]
	rows = get_base_price_rows_by_key(item_codes, [name for name in price_lists if name])
	rates = {name: {} for name in price_lists}
	for (item_code, price_list), row in rows.items():
		rates[price_list][item_code] = flt(row.price_list_rate)
	return rates[prices.sale_price_list], rates[prices.compare_at_price_list]


def get_item_price(prices: MarketPrices, sale: float | None, compare_at: float | None) -> float | None:
	# An item on neither list has no price, in the primary market too.
	return None if sale is None and compare_at is None else prices.price(sale, compare_at)


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
		"facets": {**get_facets(filters), "price": get_market_price_facet()},
	}


def search(query: str, page: int = 1, page_size: int = 24, sort: str = "default", **filters) -> SearchResults:
	query = cstr(query).strip()
	if not query:
		page, page_size = max(cint(page), 1), min(max(cint(page_size), 1), MAX_PAGE_SIZE)
		return {
			"query": query,
			"products": [],
			"total": 0,
			"page": page,
			"page_size": page_size,
			"facets": {
				"brands": [],
				"colors": [],
				"sizes": [],
				"price": get_market_price_facet(),
			},
		}
	return {
		"query": query,
		**list_products(query=query, page=page, page_size=page_size, sort=sort, **filters),
	}


def get_typeahead(query: str, limit: int = 6) -> Typeahead:
	typeahead = get_search_typeahead(query, limit)
	return {
		"query": typeahead["query"],
		"corrected_query": typeahead["corrected_query"],
		"products": get_product_cards(typeahead["products"]),
		"categories": [{"title": link["label"], "url": link["url"]} for link in typeahead["categories"]],
	}


def get_recommendations(handle: str, limit: int = 8) -> list[ProductCard]:
	product_variant = frappe.db.get_value(
		"Style Attribute Variant",
		{"route": cstr(handle), "is_published": 1},
		["item_group", "configurator"],
		as_dict=True,
	)
	if not product_variant:
		return []
	return get_product_cards(
		get_recommended_products(product_variant, limit=min(max(cint(limit), 1), MAX_PAGE_SIZE))
	)


def get_product_cards_for(item_codes: list[str] | None = None, limit: int = 8) -> list[ProductCard]:
	item_codes = [cstr(code) for code in item_codes or [] if code]
	if not item_codes:
		return get_product_cards(get_product_list(page_length=min(max(cint(limit), 1), MAX_PAGE_SIZE)))
	published_codes = frappe.get_all(
		"Style Attribute Variant", filters={"name": ("in", item_codes), "is_published": 1}, pluck="name"
	)
	if not published_codes:
		return []
	cards_by_name = {
		card["name"]: card
		for card in get_product_list(product_list=published_codes, page_length=len(published_codes))
	}
	return get_product_cards([cards_by_name[code] for code in item_codes if code in cards_by_name])


def list_brands() -> list[dict]:
	brand = frappe.qb.DocType("Brand")
	item = frappe.qb.DocType("Item")
	return (
		frappe.qb.from_(brand)
		.join(item)
		.on(item.brand == brand.name)
		.select(brand.name, brand.image)
		.where(item.disabled == 0)
		.distinct()
		.orderby(brand.name)
		.run(as_dict=True)
	)


def get_facets(filters: dict) -> dict[str, list[FacetValue]]:
	# The price filters read the market's sale price list.
	key = frappe.as_json({"filters": filters, "prices": MarketPrices.current().cache_key})
	cache_key = f"{FACETS_CACHE_PREFIX}{sha256_hash(key)}"
	facets = frappe.cache.get_value(cache_key)
	if facets is None:
		facets = {key: get_facet_values(counts) for key, counts in get_listing_facet_counts(filters).items()}
		frappe.cache.set_value(cache_key, facets, expires_in_sec=FACETS_CACHE_SECONDS)
	return facets


def get_market_price_facet() -> PriceFacet:
	prices = MarketPrices.current()
	return {**get_price_facet(prices.sale_price_list), "currency": prices.currency}


@redis_cache(ttl=FACETS_CACHE_SECONDS)
def get_price_facet(sale_price_list: str | None) -> dict:
	price_range = get_price_range(sale_price_list)
	return {"min": flt(price_range.get("min_price")), "max": flt(price_range.get("max_price"))}


def get_facet_values(counts: dict[str, int]) -> list[FacetValue]:
	return [{"value": value, "count": count} for value, count in counts.items()]


def get_product(handle: str) -> Product | None:
	"""A published product by its route, or None."""
	detail = get_product_detail(cstr(handle))
	if not detail:
		return None

	product_variant, item = detail["product_variant"], detail["product"]
	prices = MarketPrices.current()
	variants = get_variants(prices, detail["available_sizes"])
	prices_paid = [variant["price"] for variant in variants if variant["price"] is not None]
	content = get_product_content(product_variant, item)
	title = content["display_name"] or item.item_name
	return {
		"id": product_variant.name,
		"handle": product_variant.route,
		"title": title,
		"vendor": item.brand,
		"color": translate_term(product_variant.attribute_value),
		"description_html": content["description"],
		"images": detail["images"],
		"collection": get_product_collection(product_variant.item_group),
		"currency": prices.currency,
		# A secondary market has no price for a product it does not sell.
		"price": min(prices_paid, default=0 if prices.uses_store_prices else None),
		"available": any(variant["available"] for variant in variants),
		"options": get_options(product_variant, detail["available_sizes"]),
		"variants": variants,
		"selected_variant_id": (detail["selected_item"] or {}).get("item_code"),
		"rating": {
			"average": flt(product_variant.average_rating),
			"count": cint(product_variant.review_count),
		},
		"seo": get_seo(content["meta_title"], title, content["meta_description"], product_variant.noindex),
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
	return get_collection_shapes(rows)


def get_collection(handle: str) -> Collection | None:
	rows = frappe.get_all(
		"Ecommerce Category",
		filters={**COLLECTION_FILTERS, "route_slug": cstr(handle)},
		fields=COLLECTION_FIELDS,
		limit=1,
	)
	return get_collection_shapes(rows)[0] if rows else None


def get_collection_filters(handle: str) -> dict:
	"""The listing filters of the menu tab's own link, as its `/products?category=` href carries them."""
	root = next((node for node in get_storefront_menu() if node["route_slug"] == handle), None)
	if not root:
		frappe.throw(_("Collection {0} not found").format(handle), frappe.DoesNotExistError)
	return {"category": root["route_slug"], "subcategory": root["item_groups"]}


def get_collection_shapes(rows: list) -> list[Collection]:
	for row in rows:
		row.label = row.display_name or row.category_name
	translated = translate_categories(rows)
	return [get_collection_shape(row, fields) for row, fields in zip(rows, translated, strict=True)]


def get_collection_shape(row, translated: dict) -> Collection:
	return {
		"handle": row.route_slug,
		"title": translated["label"],
		"description": translated["description"] or "",
		"image": row.image,
		"seo": get_seo(
			translated["meta_title"], translated["label"], translated["meta_description"], row.noindex
		),
		"updated_at": str(row.modified),
	}


def get_seo(meta_title: str | None, title: str, meta_description: str | None, noindex) -> dict:
	# `custom_title` lets a theme keep a set meta title that happens to equal the title.
	return {
		"title": meta_title or title,
		"custom_title": bool(meta_title),
		"description": meta_description or "",
		"noindex": bool(noindex),
	}


def get_product_cards(cards: list[dict]) -> list[ProductCard]:
	item_codes = [size["item_code"] for card in cards for size in card["sizes"]]
	stock = get_available_stocks(item_codes, get_ecommerce_warehouse())
	prices = MarketPrices.current()
	# A size is for sale with both a market price and stock.
	unpriced = prices.get_unpriced(item_codes)
	sellable = {code for code in item_codes if code not in unpriced and stock.get(code, {}).get("in_stock")}
	# utils.shape_product_cards titles every grid's cards; only a hand-built card lacks one.
	set_product_titles([card for card in cards if "title" not in card])
	return [get_product_card(card, sellable, prices.currency) for card in cards]


def get_product_card(card: dict, sellable: set[str], currency: str) -> ProductCard:
	# shape_product_cards leaves no price on a product the market does not sell.
	priced = card["effective_price"] is not None
	return {
		"id": card["name"],
		"handle": card["route"],
		"title": card["title"],
		"vendor": card["brand"],
		"product_type": card["item_group"],
		"color": translate_term(card["attribute_value"]),
		"image": card["image"],
		"hover_image": card["hover_image"],
		"currency": currency,
		"price": flt(card["effective_price"]) if priced else None,
		"compare_at_price": flt(card["default_price"]) if priced and cint(card["has_discount"]) else None,
		"available": priced and any(size["item_code"] in sellable for size in card["sizes"]),
		"rating": {"average": flt(card["average_rating"]), "count": cint(card["review_count"])},
		"updated_at": card["modified"],
	}


def get_product_content(product_variant, item) -> dict[str, str]:
	# The product page shows its Item's description, translated as the product's own field.
	source = {**product_variant.as_dict(), "description": item.description}
	return translate_products([source], PRODUCT_CONTENT_FIELDS)[0]


def translate_products(
	product_variants: list, fields: tuple[str, ...] = ("display_name",)
) -> list[dict[str, str]]:
	"""Product `fields` in the request language. Cards and the product page share it, so titles always match."""
	translated = translate(product_variants, list(fields), get_localization(), doctype=PRODUCT_DOCTYPE)
	return [{field: value.value for field, value in values.items()} for values in translated]


def set_product_titles(rows: list[dict]) -> list[dict]:
	"""Set each product row's `title`: its `display_name` in the request language, else its `item_name`.
	The legacy pages and the summer theme read titles here, so they match the SDK's cards."""
	for row, content in zip(rows, translate_products(rows), strict=True):
		row["title"] = content["display_name"] or row.get("item_name") or ""
	return rows


def get_variants(prices: MarketPrices, sizes: list[dict]) -> list[dict]:
	compare_at_rates, sale_rates, _sale_ends = rates_by_item_code(
		[size["item_code"] for size in sizes], prices.compare_at_price_list, prices.sale_price_list
	)
	return [
		get_variant(prices, size, sale_rates.get(size["item_code"]), compare_at_rates.get(size["item_code"]))
		for size in sizes
	]


def get_variant(prices: MarketPrices, size: dict, sale: float | None, compare_at: float | None) -> dict:
	price = prices.price(sale, compare_at)
	stock = size["stock_detail"]
	return {
		"id": size["item_code"],
		"title": translate_term(size["size"]),
		"size": size["size"],
		"price": price,
		"compare_at_price": prices.compare_at(price, compare_at),
		"available": price is not None and bool(stock.get("in_stock")),
		"quantity_available": None if stock.get("unlimited") else flt(stock.get("stock_qty")),
	}


def get_options(product_variant, sizes: list[dict]) -> list[ProductOption]:
	"""The colour axis links sibling products; the size axis picks a variant. Fallback axes stay hidden."""
	options = []
	attribute = frappe.db.get_value(
		"Style Attribute Configurator", product_variant.configurator, "item_attribute"
	)
	if attribute and attribute != DEFAULT_OPTION_ATTRIBUTE:
		options.append({"name": translate_term(attribute), "values": get_sibling_values(product_variant)})
	if len(sizes) > 1 or (sizes and sizes[0]["size"] != DEFAULT_SIZE_VALUE):
		values = [{"name": translate_term(size["size"]), "value": size["size"]} for size in sizes]
		options.append({"name": _("Size", lang=get_localization().language.code), "values": values})
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
			"name": translate_term(sibling.attribute_value),
			"value": sibling.attribute_value,
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


def translate_term(term: str | None) -> str | None:
	# Option names and values are shared terms: one Frappe Translation covers every product.
	return _(term, lang=get_localization().language.code) if term else term


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
