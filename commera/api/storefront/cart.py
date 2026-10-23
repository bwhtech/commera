import time
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cint, cstr, sha256_hash

from commera.commera_ecommerce.doctype.commera_cart.commera_cart import (
	adopt_guest_cart,
	get_session_cart,
	set_guest_cart_key,
)
from commera.guest import (
	CART_TOKEN_HEADER,
	get_guest_cart_token,
	is_guest,
	set_guest_cart_cookie,
	validate_cart_token,
)
from commera.sdk import cart as cart_sdk
from commera.sdk.types import PricedCart
from commera.utils import get_next_url

CHECKOUT_CODE_PREFIX = "commera:storefront_checkout:"
CHECKOUT_CODE_SECONDS = 5 * 60
CHECKOUT_SIGN_IN_SECONDS = 10 * 60


# Each call acts on the cart of the X-Commera-Cart-Token header the storefront server sends.
@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=1200, seconds=60 * 60)
def get_cart() -> PricedCart | None:
	return cart_sdk.get_priced_cart()


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60 * 60)
def add_lines(lines: list | str | None = None) -> PricedCart:
	"""Add `[{item_code, qty, attributes}]`; only items a published product sells."""
	lines = [
		{
			"item_code": cstr(line.get("item_code")),
			"qty": cint(line.get("qty") or 1),
			"attributes": line.get("attributes"),
		}
		for line in get_list_of(lines, dict, _("Send the lines as a list of objects."))
	]
	return cart_sdk.add_lines(lines)


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60 * 60)
def update_lines(lines: list | str | None = None) -> PricedCart:
	"""Set `[{line_id, qty}]`; a quantity of 0 removes the line."""
	lines = [
		{"line_id": cstr(line.get("line_id")), "qty": cint(line.get("qty"))}
		for line in get_list_of(lines, dict, _("Send the lines as a list of objects."))
	]
	return cart_sdk.update_lines(lines)


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60 * 60)
def remove_lines(line_ids: list | str | None = None) -> PricedCart:
	return cart_sdk.remove_lines(get_list_of(line_ids, str, _("Send the line ids as a list of strings.")))


def get_list_of(value: list | str | None, item_type: type, message: str) -> list:
	try:
		value = frappe.parse_json(value)
	except ValueError:
		value = None
	if not isinstance(value, list) or not all(isinstance(item, item_type) for item in value):
		frappe.throw(message)
	return value


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
	# An account code outlives a guest one: the browser may have to sign in before it can use it.
	handoff["expires_at"] = (
		time.time() + CHECKOUT_CODE_SECONDS + (CHECKOUT_SIGN_IN_SECONDS if "user" in handoff else 0)
	)
	frappe.cache.set_value(
		f"{CHECKOUT_CODE_PREFIX}{code}",
		handoff,
		expires_in_sec=CHECKOUT_CODE_SECONDS + CHECKOUT_SIGN_IN_SECONDS,
	)
	return {"path": f"/api/method/commera.api.storefront.cart.open_checkout?code={code}"}


def get_checkout_handoff() -> dict:
	"""The guest's cart token, or the signed-in shopper whose account cart the checkout opens."""
	if not is_guest():
		return {"user": frappe.session.user}
	if token := get_guest_cart_token():
		return {"token": token}
	frappe.throw(_("Send the cart token to start a storefront checkout."))


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=60, seconds=60)
def open_checkout(code: str):
	"""Send the browser on with a checkout code. It writes nothing, so a link preview cannot use the code up."""
	handoff = get_checkout_code(f"{CHECKOUT_CODE_PREFIX}{cstr(code)}")
	if not handoff:
		return redirect(f"/{frappe.local.lang}/cart")
	if "user" in handoff:
		return open_account_checkout(handoff)
	redirect(get_handoff_page_url(code))


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=60, seconds=60)
def claim_checkout_cart(code: str):
	"""Move a guest checkout code's cart to this guest browser, then go on to checkout."""
	if not is_guest():
		return redirect(get_handoff_page_url(code))
	key = f"{CHECKOUT_CODE_PREFIX}{cstr(code)}"
	handoff = get_checkout_code(key)
	if not handoff or "token" not in handoff:
		return redirect(f"/{frappe.local.lang}/cart")

	frappe.cache.delete_value(key)
	# A new token, so the storefront's copy of the old one no longer reaches the cart.
	set_guest_cart_key(sha256_hash(handoff["token"]), set_guest_cart_cookie(frappe.generate_hash(length=32)))
	redirect(get_next_url())


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60 * 60, user_based=True)
def adopt_checkout_cart(code: str):
	"""Merge the guest cart of a checkout code into the signed-in shopper's cart, then go on to checkout."""
	key = f"{CHECKOUT_CODE_PREFIX}{cstr(code)}"
	handoff = get_checkout_code(key)
	if not handoff or "token" not in handoff:
		return redirect(f"/{frappe.local.lang}/cart")

	frappe.cache.delete_value(key)
	adopt_guest_cart(sha256_hash(handoff["token"]))
	redirect(get_next_url())


def get_handoff_page_url(code: str) -> str:
	params = {key: value for key, value in frappe.form_dict.items() if key not in ("cmd", "csrf_token")}
	return f"/storefront-cart?{urlencode({**params, 'code': code})}"


def get_checkout_code(key: str) -> dict | None:
	handoff = frappe.cache.get_value(key)
	if handoff and handoff["expires_at"] > time.time():
		return handoff
	return None


def open_account_checkout(handoff: dict):
	"""Only a browser signed in as the code's user goes on to checkout. Any other browser signs in first."""
	if frappe.session.user == handoff["user"]:
		return redirect(get_next_url())
	redirect(f"/storefront-login?{urlencode({'prompt': 'login', 'redirect-to': frappe.request.full_path})}")


def redirect(location: str):
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = location
