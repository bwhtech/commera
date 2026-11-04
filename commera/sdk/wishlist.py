import frappe
from frappe import _
from frappe.utils.data import cstr

from commera.sdk.account import get_shopper
from commera.sdk.catalog import get_product_cards_for
from commera.sdk.types import Wishlist

__all__ = ["add_to_wishlist", "get_wishlist", "remove_from_wishlist"]


def get_wishlist() -> Wishlist:
	products = frappe.get_all(
		"Commera Wishlist Item", filters={"user": get_shopper()}, pluck="product", order_by="creation desc"
	)
	cards = get_product_cards_for(products) if products else []
	return {"products": cards, "count": len(cards)}


def add_to_wishlist(product: str) -> Wishlist:
	shopper = get_shopper()
	product = get_published_product(product)
	if not frappe.db.exists("Commera Wishlist Item", {"user": shopper, "product": product}):
		try:
			frappe.get_doc({"doctype": "Commera Wishlist Item", "user": shopper, "product": product}).insert(
				ignore_permissions=True
			)
		except frappe.UniqueValidationError:
			frappe.clear_last_message()
	return get_wishlist()


def remove_from_wishlist(product: str) -> Wishlist:
	shopper = get_shopper()
	product = cstr(product)
	products = frappe.get_all(
		"Style Attribute Variant", or_filters={"name": product, "route": product}, pluck="name"
	)
	if products:
		frappe.db.delete("Commera Wishlist Item", {"user": shopper, "product": ("in", products)})
	return get_wishlist()


def get_published_product(product: str) -> str:
	product = cstr(product)
	published = frappe.get_all(
		"Style Attribute Variant",
		filters={"is_published": 1},
		or_filters={"name": product, "route": product},
		pluck="name",
		limit=1,
	)
	if not published:
		frappe.throw(_("Product {0} not found").format(product), frappe.DoesNotExistError)
	return published[0]
