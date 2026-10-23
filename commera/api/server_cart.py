import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cint, cstr

from commera.api.shipping import get_checkout_summary
from commera.commera_ecommerce.doctype.commera_cart.commera_cart import (
	MAX_CART_LINES,
	CommeraCart,
	get_quantities_by_item_code,
	get_session_cart,
)
from commera.discounts.selection import get_discount_codes
from commera.sdk import cart as cart_sdk
from commera.www.cart.permalink import get_cart_lines


# Guests hold carts before signing in; the cart cookie scopes each call to the caller's own cart.
@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=1200, seconds=60 * 60)
def get_server_cart() -> dict | None:
	cart = get_session_cart()
	return get_cart_state(cart) if cart else None


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60 * 60)
def sync_server_cart(items: list | str, version: str | None = None) -> dict:
	# A stale browser version writes nothing; the server cart comes back instead.
	quantities = get_browser_quantities(items)
	selection = get_browser_selection(items)
	cart = get_session_cart(create=bool(quantities))
	if not cart:
		return {"version": None}
	if version and not cart.is_new() and version != cart.version:
		return {"conflict": True, **get_cart_state(cart)}

	changed = cart.set_quantities(quantities)
	if cart.set_selection(selection) or changed or cart.is_new():
		cart.save(ignore_permissions=True)
	return {"version": cart.version}


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60 * 60)
def get_priced_server_cart() -> dict | None:
	return cart_sdk.get_priced_cart()


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=30, seconds=60 * 60)
def apply_discount_code(code: str) -> dict:
	return {**cart_sdk.add_discount_code(cstr(code).strip()), "checkout_summary": get_open_checkout_summary()}


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=100, seconds=60 * 60)
def remove_discount_code(code: str) -> dict:
	return {
		**cart_sdk.remove_discount_code(cstr(code).strip()),
		"checkout_summary": get_open_checkout_summary(),
	}


def get_open_checkout_summary() -> dict | None:
	quotation = cart_sdk.get_open_cart_quotation()
	return get_checkout_summary(quotation) if quotation else None


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


def get_browser_selection(items: list | str) -> dict[str, bool]:
	selection = {}
	for entry in frappe.parse_json(items) or []:
		item_code = cstr(entry.get("item_code")).strip()
		selection[item_code] = selection.get(item_code, False) or bool(cint(entry.get("selected", 1)))
	return selection


def get_cart_state(cart: CommeraCart) -> dict:
	selected_item_codes = {row.item_code for row in cart.get_selected_lines()}
	lines = get_cart_lines(get_quantities_by_item_code(cart.lines), [])
	for line in lines:
		line["selected"] = line["variant"]["item_code"] in selected_item_codes
	return {
		"version": cart.version,
		"lines": lines,
		"discount_codes": get_discount_codes(cart),
	}
