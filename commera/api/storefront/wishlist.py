import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cstr

from commera.sdk import wishlist
from commera.sdk.types import Wishlist


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=300, seconds=60, user_based=True)
def get_wishlist() -> Wishlist:
	return wishlist.get_wishlist()


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=300, seconds=60 * 60, user_based=True)
def add_to_wishlist(product: str) -> Wishlist:
	return wishlist.add_to_wishlist(cstr(product))


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=300, seconds=60 * 60, user_based=True)
def remove_from_wishlist(product: str) -> Wishlist:
	return wishlist.remove_from_wishlist(cstr(product))
