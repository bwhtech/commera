import frappe
from frappe import _
from frappe.utils.data import cint, cstr, flt

from commera.api.storefront import rate_limited_guest_api
from commera.sdk import catalog
from commera.sdk.types import Product, ProductPage
from commera.storefront_cache import (
	ALLOWED_CACHED_PAGE_SIZES,
	CATALOG_READ_DOMAINS,
	MAX_CACHED_PAGE,
	PDP_DOMAINS,
	cached_guest_api,
)


@rate_limited_guest_api("GET", limit=600, seconds=60)
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
) -> ProductPage:
	"""List values may be comma separated."""
	norm_collection = collection or None
	norm_query = cstr(query).strip()
	norm_brands = get_list(brands)
	norm_colors = get_list(colors)
	norm_sizes = get_list(sizes)
	norm_min = None if min_price in (None, "") else flt(min_price)
	norm_max = None if max_price in (None, "") else flt(max_price)
	norm_on_sale = bool(cint(on_sale))
	norm_page = cint(page) or 1
	norm_page_size = cint(page_size) or 24

	def _compute():
		return catalog.list_products(
			collection=norm_collection,
			query=query,
			brands=norm_brands,
			colors=norm_colors,
			sizes=norm_sizes,
			min_price=norm_min,
			max_price=norm_max,
			on_sale=norm_on_sale,
			sort=sort,
			page=norm_page,
			page_size=norm_page_size,
		)

	# Free-text search, continuous price bounds, or unbounded pagination bypass Redis cache.
	if (
		norm_query
		or norm_min is not None
		or norm_max is not None
		or norm_page < 1
		or norm_page > MAX_CACHED_PAGE
		or norm_page_size not in ALLOWED_CACHED_PAGE_SIZES
	):
		return _compute()

	key_parts = (
		norm_collection,
		tuple(norm_brands),
		tuple(norm_colors),
		tuple(norm_sizes),
		norm_on_sale,
		sort,
		norm_page,
		norm_page_size,
	)

	return cached_guest_api(
		"products.get_products",
		key_parts,
		CATALOG_READ_DOMAINS,
		_compute,
		endpoint="commera.api.storefront.products.get_products",
		ttl=60,
	)


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_product(handle: str) -> Product:
	def _build():
		if product := catalog.get_product(handle):
			return product
		frappe.throw(_("Product {0} not found").format(handle), frappe.DoesNotExistError)

	return cached_guest_api(
		"products.get_product",
		handle,
		PDP_DOMAINS,
		_build,
		endpoint="commera.api.storefront.products.get_product",
		ttl=60,
	)


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_wishlist_prices(handles: list | str) -> list[dict]:
	if isinstance(handles, str):
		handles = frappe.parse_json(handles)
	if not isinstance(handles, list) or len(handles) > 100:
		frappe.throw(_("Invalid wishlist product list"), frappe.ValidationError)
	if any(not isinstance(handle, str) or len(handle) > 140 for handle in handles):
		frappe.throw(_("Invalid wishlist product list"), frappe.ValidationError)
	if not handles:
		return []
	deduped = list(dict.fromkeys(handles))
	names = frappe.get_all(
		"Style Attribute Variant",
		filters={"route": ("in", deduped), "is_published": 1},
		pluck="name",
	)
	cards = {card["handle"]: card for card in catalog.get_product_cards_for(names)} if names else {}
	return [
		{
			"handle": handle,
			**{key: cards[handle][key] for key in ("price", "compare_at_price", "currency", "available")},
		}
		if handle in cards
		else {"handle": handle, "price": None, "compare_at_price": None, "available": False}
		for handle in deduped
	]


def get_list(value: list | str | None) -> list[str]:
	if isinstance(value, str):
		value = value.split(",")
	return [cstr(entry).strip() for entry in value or [] if cstr(entry).strip()]
