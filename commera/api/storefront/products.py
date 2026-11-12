import frappe
from frappe import _
from frappe.utils.data import cint, cstr, flt

from commera.api.storefront import rate_limited_guest_api
from commera.sdk import catalog
from commera.sdk.types import Product, ProductPage


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
	return catalog.list_products(
		collection=collection or None,
		query=query,
		brands=get_list(brands),
		colors=get_list(colors),
		sizes=get_list(sizes),
		min_price=None if min_price in (None, "") else flt(min_price),
		max_price=None if max_price in (None, "") else flt(max_price),
		on_sale=bool(cint(on_sale)),
		sort=sort,
		page=page,
		page_size=page_size,
	)


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_product(handle: str) -> Product:
	if product := catalog.get_product(handle):
		return product
	frappe.throw(_("Product {0} not found").format(handle), frappe.DoesNotExistError)


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
	names = frappe.get_all(
		"Style Attribute Variant",
		filters={"route": ("in", handles), "is_published": 1},
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
		for handle in dict.fromkeys(handles)
	]


def get_list(value: list | str | None) -> list[str]:
	if isinstance(value, str):
		value = value.split(",")
	return [cstr(entry).strip() for entry in value or [] if cstr(entry).strip()]
