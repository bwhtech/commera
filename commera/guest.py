import frappe
from frappe import _
from frappe.utils.data import cint, sha256_hash

GUEST_CART_COOKIE = "commera_guest_cart"
GUEST_CART_COOKIE_MAX_AGE = 30 * 24 * 60 * 60


def is_guest() -> bool:
	return frappe.session.user == "Guest"


def is_guest_checkout_enabled() -> bool:
	return bool(cint(frappe.get_cached_value("Commera Settings", "Commera Settings", "allow_guest_checkout")))


def validate_guest_checkout_enabled():
	if not is_guest_checkout_enabled():
		raise frappe.PermissionError(_("Please sign in to check out."))


def get_guest_cart_token() -> str | None:
	request = getattr(frappe.local, "request", None)
	return request.cookies.get(GUEST_CART_COOKIE) if request else None


def get_guest_cart_key() -> str | None:
	token = get_guest_cart_token()
	return sha256_hash(token) if token else None


def set_guest_cart_cookie() -> str:
	"""Keep the browser's cart token, or issue one, and return the key the cart is stored under."""
	token = get_guest_cart_token() or frappe.generate_hash(length=32)
	frappe.local.cookie_manager.set_cookie(
		GUEST_CART_COOKIE, token, max_age=GUEST_CART_COOKIE_MAX_AGE, httponly=True, samesite="Lax"
	)
	return sha256_hash(token)


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
