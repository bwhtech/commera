import re

import frappe
from frappe import _
from frappe.utils.data import cint, sha256_hash

GUEST_CART_COOKIE = "commera_guest_cart"
GUEST_CART_COOKIE_MAX_AGE = 30 * 24 * 60 * 60
# Headless storefronts keep the token themselves and send it on each server-to-server call.
CART_TOKEN_HEADER = "X-Commera-Cart-Token"
CART_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,128}")


def is_guest() -> bool:
	return frappe.session.user == "Guest"


def is_guest_checkout_enabled() -> bool:
	return bool(cint(frappe.get_cached_value("Commera Settings", "Commera Settings", "allow_guest_checkout")))


def validate_guest_checkout_enabled():
	if not is_guest_checkout_enabled():
		raise frappe.PermissionError(_("Please sign in to check out."))


def get_guest_cart_token() -> str | None:
	request = getattr(frappe.local, "request", None)
	if not request:
		return None
	if token := request.headers.get(CART_TOKEN_HEADER):
		validate_cart_token(token)
		return token
	return request.cookies.get(GUEST_CART_COOKIE)


def validate_cart_token(token: str):
	if not CART_TOKEN_PATTERN.fullmatch(token):
		frappe.throw(_("A cart token is 32 to 128 letters, digits, hyphens or underscores."))


def get_guest_cart_key() -> str | None:
	token = get_guest_cart_token()
	return sha256_hash(token) if token else None


def set_guest_cart_cookie(token: str | None = None) -> str:
	"""Keep the given or the browser's cart token, or issue one, and return the key the cart is stored under."""
	token = token or get_guest_cart_token() or frappe.generate_hash(length=32)
	frappe.local.cookie_manager.set_cookie(
		GUEST_CART_COOKIE, token, max_age=GUEST_CART_COOKIE_MAX_AGE, httponly=True, samesite="Lax"
	)
	return sha256_hash(token)


def clear_guest_cart_cookie():
	frappe.local.cookie_manager.delete_cookie(GUEST_CART_COOKIE)


def get_guest_cart_name(cart_key: str | None = None) -> str | None:
	cart_key = cart_key or get_guest_cart_key()
	if not cart_key:
		return None
	return frappe.db.get_value(
		"Quotation",
		{"custom_guest_cart_key": cart_key, "order_type": "Shopping Cart", "docstatus": 0},
		"name",
		order_by="modified desc",
	)


def is_guest_cart(quotation_name: str | None) -> bool:
	# Not limited to drafts: the confirmation page asks about the cart after checkout has submitted it.
	cart_key = get_guest_cart_key()
	return bool(
		cart_key
		and quotation_name
		and frappe.db.exists("Quotation", {"name": quotation_name, "custom_guest_cart_key": cart_key})
	)
