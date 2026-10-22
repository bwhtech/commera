from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cint, cstr, sha256_hash

from commera.commera_ecommerce.doctype.commera_cart.commera_cart import adopt_guest_cart, get_session_cart
from commera.guest import (
	CART_TOKEN_HEADER,
	get_guest_cart_token,
	is_guest,
	set_guest_cart_cookie,
	validate_cart_token,
)
from commera.plugin_events import get_listed_items
from commera.sdk import cart as cart_sdk
from commera.sdk.types import PricedCart
from commera.www.cart.permalink import get_next_url

CHECKOUT_CODE_PREFIX = "commera:storefront_checkout:"
CHECKOUT_CODE_SECONDS = 5 * 60


# Each call acts on the cart of the X-Commera-Cart-Token header the storefront server sends.
@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=1200, seconds=60 * 60)
def get_cart() -> PricedCart | None:
	return cart_sdk.get_priced_cart()


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60 * 60)
def add_lines(lines: list | str) -> PricedCart:
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
	return cart_sdk.add_lines(lines)


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60 * 60)
def update_lines(lines: list | str) -> PricedCart:
	"""Set `[{line_id, qty}]`; a quantity of 0 removes the line."""
	lines = [
		{"line_id": cstr(line.get("line_id")), "qty": cint(line.get("qty"))}
		for line in frappe.parse_json(lines) or []
	]
	return cart_sdk.update_lines(lines)


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60 * 60)
def remove_lines(line_ids: list | str) -> PricedCart:
	return cart_sdk.remove_lines([cstr(line_id) for line_id in frappe.parse_json(line_ids)])


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=30, seconds=60 * 60)
def add_discount_code(code: str) -> PricedCart:
	return cart_sdk.add_discount_code(cstr(code).strip())


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=100, seconds=60 * 60)
def remove_discount_code(code: str) -> PricedCart:
	return cart_sdk.remove_discount_code(cstr(code).strip())


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60 * 60, user_based=True)
def adopt_cart() -> PricedCart | None:
	"""Move the guest cart of the X-Commera-Cart-Token header into the signed-in shopper's cart."""
	token = frappe.request.headers.get(CART_TOKEN_HEADER)
	if not token:
		frappe.throw(_("Send the cart token of the cart to adopt."))
	validate_cart_token(token)
	adopt_guest_cart(sha256_hash(token))
	return cart_sdk.get_priced_cart()


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=120, seconds=60 * 60)
def get_checkout_url() -> dict:
	"""A single-use path that opens this cart in the Commera checkout, valid for five minutes."""
	handoff = get_checkout_handoff()
	if not get_session_cart():
		frappe.throw(_("Add something to your cart first."), frappe.DoesNotExistError)

	code = frappe.generate_hash(length=32)
	frappe.cache.set_value(f"{CHECKOUT_CODE_PREFIX}{code}", handoff, expires_in_sec=CHECKOUT_CODE_SECONDS)
	return {"path": f"/api/method/commera.api.storefront.cart.open_checkout?code={code}"}


def get_checkout_handoff() -> str | dict:
	"""The guest's cart token, or the signed-in shopper whose account cart the checkout opens."""
	if not is_guest():
		return {"user": frappe.session.user}
	if token := get_guest_cart_token():
		return token
	frappe.throw(_("Send the cart token to start a storefront checkout."))


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=60, seconds=60)
def open_checkout(code: str):
	"""Bind the storefront cart to this browser, then go on to checkout. A used or old code opens the cart."""
	key = f"{CHECKOUT_CODE_PREFIX}{cstr(code)}"
	handoff = frappe.cache.get_value(key)
	if isinstance(handoff, dict):
		return open_account_checkout(key, handoff["user"])

	frappe.cache.delete_value(key)
	if handoff and is_guest():
		set_guest_cart_cookie(handoff)
	elif handoff:
		adopt_guest_cart(sha256_hash(handoff))
		# A GET is not committed unless asked; the merge must persist.
		frappe.local.flags.commit = True

	redirect(get_next_url() if handoff else f"/{frappe.local.lang}/cart")


def open_account_checkout(key: str, user: str):
	"""Only a browser signed in as `user` uses the code. Any other browser signs in first, then comes back."""
	if frappe.session.user == user:
		frappe.cache.delete_value(key)
		return redirect(get_next_url())

	# The sign-in can take longer than the code would otherwise live.
	frappe.cache.set_value(key, {"user": user}, expires_in_sec=CHECKOUT_CODE_SECONDS)
	redirect(f"/storefront-login?{urlencode({'prompt': 'login', 'redirect-to': frappe.request.full_path})}")


def redirect(location: str):
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = location
