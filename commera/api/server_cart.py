import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cint, cstr

from commera.commera_ecommerce.doctype.commera_cart.commera_cart import (
	MAX_CART_LINES,
	CommeraCart,
	get_session_cart,
)
from commera.discount_codes import get_discount_codes
from commera.sdk import cart as cart_sdk
from commera.www.cart.permalink import get_cart_lines


# Guests hold carts before signing in; the cart cookie scopes each call to the caller's own cart.
@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep: guest-whitelisted-method
def get_server_cart() -> dict | None:
	cart = get_session_cart()
	return get_cart_state(cart) if cart else None


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60 * 60)
def sync_server_cart(items: list | str, version: str | None = None) -> dict:
	"""Copy the browser cart's quantities to the server cart. When the server cart changed after the
	browser last saw it, nothing is written and the server cart comes back for the browser to show."""
	quantities = get_browser_quantities(items)
	cart = get_session_cart(create=bool(quantities))
	if not cart:
		return {"version": None}
	if version and not cart.is_new() and version != cart.version:
		return {"conflict": True, **get_cart_state(cart)}

	if cart.set_quantities(quantities) or cart.is_new():
		cart.save(ignore_permissions=True)
	return {"version": cart.version}


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep: guest-whitelisted-method
def get_priced_server_cart() -> dict | None:
	return cart_sdk.get_priced_cart()


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=30, seconds=60 * 60)
def apply_discount_code(code: str) -> dict:
	return cart_sdk.add_discount_code(cstr(code).strip())


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
def remove_discount_code(code: str) -> dict:
	return cart_sdk.remove_discount_code(cstr(code).strip())


def get_browser_quantities(items: list | str) -> dict[str, int]:
	quantities = {}
	for entry in frappe.parse_json(items) or []:
		item_code = cstr(entry.get("item_code")).strip()
		qty = cint(entry.get("qty"))
		if not item_code or qty < 1:
			frappe.throw(_("Each cart line needs an item code and a quantity of at least 1."))
		quantities[item_code] = quantities.get(item_code, 0) + qty
	if len(quantities) > MAX_CART_LINES:
		frappe.throw(_("A cart holds at most {0} lines.").format(MAX_CART_LINES))
	return quantities


def get_cart_state(cart: CommeraCart) -> dict:
	"""The server cart as storefront cart lines, so the browser can replace its own copy."""
	quantities = {}
	for row in cart.lines:
		quantities[row.item_code] = quantities.get(row.item_code, 0) + cint(row.qty)
	return {
		"version": cart.version,
		"lines": get_cart_lines(quantities, []),
		"discount_codes": get_discount_codes(cart),
	}
