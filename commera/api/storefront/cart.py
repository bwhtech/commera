import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cint, cstr, sha256_hash

from commera.commera_ecommerce.doctype.commera_cart.commera_cart import adopt_guest_cart, get_session_cart
from commera.guest import get_guest_cart_token, is_guest, set_guest_cart_cookie
from commera.plugin_events import get_listed_items
from commera.sdk import cart as cart_sdk
from commera.search.record_builder import images_for_variants
from commera.www.cart.permalink import get_next_url

CHECKOUT_CODE_PREFIX = "commera:storefront_checkout:"
CHECKOUT_CODE_SECONDS = 5 * 60


# Each call acts on the cart of the X-Commera-Cart-Token header the storefront server sends.
@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=1200, seconds=60 * 60)
def get_cart() -> dict | None:
	return get_cart_shape(cart_sdk.get_priced_cart())


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60 * 60)
def add_lines(lines: list | str) -> dict:
	"""Add `[{item_code, qty, attributes}]`; only items a published product sells."""
	lines = [
		{
			"item_code": cstr(line.get("item_code")),
			"qty": cint(line.get("qty") or 1),
			"attributes": line.get("attributes"),
		}
		for line in frappe.parse_json(lines) or []
	]
	if unlisted := {line["item_code"] for line in lines} - get_listed_items(
		[line["item_code"] for line in lines]
	):
		frappe.throw(_("{0} is not for sale.").format(", ".join(sorted(unlisted))))
	return get_cart_shape(cart_sdk.add_lines(lines))


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60 * 60)
def update_lines(lines: list | str) -> dict:
	"""Set `[{line_id, qty}]`; a quantity of 0 removes the line."""
	lines = [
		{"line_id": cstr(line.get("line_id")), "qty": cint(line.get("qty"))}
		for line in frappe.parse_json(lines) or []
	]
	return get_cart_shape(cart_sdk.update_lines(lines))


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60 * 60)
def remove_lines(line_ids: list | str) -> dict:
	return get_cart_shape(cart_sdk.remove_lines([cstr(line_id) for line_id in frappe.parse_json(line_ids)]))


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=30, seconds=60 * 60)
def add_discount_code(code: str) -> dict:
	return get_cart_shape(cart_sdk.add_discount_code(cstr(code).strip()))


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=100, seconds=60 * 60)
def remove_discount_code(code: str) -> dict:
	return get_cart_shape(cart_sdk.remove_discount_code(cstr(code).strip()))


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=120, seconds=60 * 60)
def get_checkout_url() -> dict:
	"""A single-use path that opens this cart in the Commera checkout, valid for five minutes."""
	token = get_guest_cart_token()
	if not is_guest() or not token:
		frappe.throw(_("Send the cart token to start a storefront checkout."))
	if not get_session_cart():
		frappe.throw(_("Add something to your cart first."), frappe.DoesNotExistError)

	code = frappe.generate_hash(length=32)
	frappe.cache.set_value(f"{CHECKOUT_CODE_PREFIX}{code}", token, expires_in_sec=CHECKOUT_CODE_SECONDS)
	return {"path": f"/api/method/commera.api.storefront.cart.open_checkout?code={code}"}


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=60, seconds=60)
def open_checkout(code: str):
	"""Bind the storefront cart to this browser, then go on to checkout. A used or old code opens the cart."""
	key = f"{CHECKOUT_CODE_PREFIX}{cstr(code)}"
	token = frappe.cache.get_value(key)
	frappe.cache.delete_value(key)
	if token and is_guest():
		set_guest_cart_cookie(token)
	elif token:
		adopt_guest_cart(sha256_hash(token))
		# A GET is not committed unless asked; the merge must persist.
		frappe.local.flags.commit = True

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = get_next_url() if token else f"/{frappe.local.lang}/cart"


def get_cart_shape(priced_cart: dict | None) -> dict | None:
	"""The priced cart, with the product each line belongs to."""
	if not priced_cart:
		return None
	products = get_line_products([line["item_code"] for line in priced_cart["lines"]])
	lines = [{**line, "product": products.get(line["item_code"])} for line in priced_cart["lines"]]
	return {**priced_cart, "lines": lines, "total_quantity": sum(line["qty"] for line in lines)}


def get_line_products(item_codes: list[str]) -> dict[str, dict]:
	rows = frappe.get_all(
		"Color Size Item",
		filters={"item_code": ("in", item_codes or [""]), "parenttype": "Style Attribute Variant"},
		fields=["item_code", "size", "parent"],
	)
	variants = {
		row.name: row
		for row in frappe.get_all(
			"Style Attribute Variant",
			filters={"name": ("in", [row.parent for row in rows] or [""]), "is_published": 1},
			fields=["name", "route", "display_name"],
		)
	}
	images = images_for_variants(list(variants))
	return {
		row.item_code: {
			"handle": variants[row.parent].route,
			"title": variants[row.parent].display_name,
			"variant_title": row.size,
			"image": images.get(row.parent, {}).get("image"),
		}
		for row in rows
		if row.parent in variants
	}
