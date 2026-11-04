import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cint, cstr, flt

from commera.sdk import catalog
from commera.sdk.types import Product, ProductPage


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


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60)
def get_product(handle: str) -> Product:
	if product := catalog.get_product(handle):
		return product
	frappe.throw(_("Product {0} not found").format(handle), frappe.DoesNotExistError)


def get_list(value: list | str | None) -> list[str]:
	if isinstance(value, str):
		value = value.split(",")
	return [cstr(entry).strip() for entry in value or [] if cstr(entry).strip()]
