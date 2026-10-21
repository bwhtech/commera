import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cint, cstr, flt

from commera.api.admin.catalog import DEFAULT_OPTION_ATTRIBUTE, DEFAULT_SIZE_VALUE
from commera.api.storefront.collections import get_collection_handle, get_item_group
from commera.product_detail import get_product_detail
from commera.search.facets import get_product_filters
from commera.search.record_builder import rates_by_item_code, sizes_for_variants
from commera.swatches import get_swatch_map
from commera.utils import get_available_stocks, get_product_list, get_total_product_count

SORT_KEYS = ("default", "price_low", "price_high", "name", "new_arrival", "discount")
MAX_PAGE_SIZE = 48


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60)
def get_products(
	collection: str | None = None,
	query: str | None = None,
	brands: list | str | None = None,
	colors: list | str | None = None,
	sizes: list | str | None = None,
	min_price: float | None = None,
	max_price: float | None = None,
	on_sale: bool | int = 0,
	sort: str = "default",
	page: int = 1,
	page_size: int = 24,
) -> dict:
	"""One page of published products with the facets of the whole result."""
	if sort not in SORT_KEYS:
		frappe.throw(_("Sort must be one of {0}.").format(", ".join(SORT_KEYS)))
	page, page_size = max(cint(page), 1), min(max(cint(page_size), 1), MAX_PAGE_SIZE)
	filters = {
		"subcategory": [get_item_group(collection)] if collection else [],
		"search": cstr(query).strip(),
		"brands": get_list(brands),
		"colors": get_list(colors),
		"sizes": get_list(sizes),
		"has_discount": bool(cint(on_sale)),
		"category": "",
		**({"min_price": flt(min_price)} if min_price not in (None, "") else {}),
		**({"max_price": flt(max_price)} if max_price not in (None, "") else {}),
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


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60)
def get_product(handle: str) -> dict:
	"""A published product: one colour of a style, with its sizes as the variants."""
	detail = get_product_detail(cstr(handle))
	if not detail:
		raise frappe.DoesNotExistError(_("Product {0} not found").format(handle))

	product_variant, item = detail["product_variant"], detail["product"]
	variants = get_variants(detail["available_sizes"])
	prices = [variant["price"] for variant in variants]
	return {
		"id": product_variant.name,
		"handle": product_variant.route,
		"title": product_variant.display_name or item.item_name,
		"vendor": item.brand,
		"color": product_variant.attribute_value,
		"description_html": item.description or "",
		"images": detail["images"],
		"collection": get_product_collection(product_variant.item_group),
		"currency": get_currency(),
		"price": min(prices, default=0),
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


def get_list(value: list | str | None) -> list[str]:
	if isinstance(value, str):
		value = value.split(",")
	return [cstr(entry).strip() for entry in value or [] if cstr(entry).strip()]


def get_currency() -> str:
	return frappe.get_cached_value("Price List", get_settings().get_sale_price_list(), "currency")


def get_settings():
	return frappe.get_cached_doc("Commera Settings")


def get_product_cards(cards: list[dict]) -> list[dict]:
	item_codes = [size["item_code"] for card in cards for size in card["sizes"]]
	stock = get_available_stocks(item_codes, get_settings().ecommerce_warehouse)
	currency = get_currency()
	return [get_product_card(card, stock, currency) for card in cards]


def get_product_card(card: dict, stock: dict, currency: str) -> dict:
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
	settings = get_settings()
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


def get_options(product_variant, sizes: list[dict]) -> list[dict]:
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
	stock = get_available_stocks(item_codes, get_settings().ecommerce_warehouse)
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
