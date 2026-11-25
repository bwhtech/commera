import frappe
from frappe import _
from frappe.utils.data import cstr, flt

from commera.api.storefront import rate_limited_guest_api
from commera.sdk import checkout
from commera.sdk.types import (
	CheckoutResult,
	CheckoutState,
	PaymentMethod,
	PaymentSession,
	PickupLocation,
	ShippingOptions,
)


@rate_limited_guest_api("GET", limit=1200, seconds=60 * 60)
def get() -> CheckoutState | None:
	from commera.guest import get_guest_cart_key, is_guest, validate_guest_checkout_enabled
	from commera.plugin_events import get_handlers
	from commera.storefront_cache import cached_checkout_response, is_cache_enabled

	if not is_cache_enabled() or get_handlers("commera_hooks", "cart_fees"):
		return checkout.get()

	if is_guest():
		validate_guest_checkout_enabled()
		cart_key = get_guest_cart_key()
		if not cart_key:
			return None
		meta = frappe.db.get_value(
			"Quotation",
			{"custom_guest_cart_key": cart_key, "order_type": "Shopping Cart", "docstatus": 0},
			["name", "modified"],
			order_by="modified desc",
			as_dict=True,
		)
	else:
		meta = frappe.db.get_value(
			"Quotation",
			{"contact_email": frappe.session.user, "order_type": "Shopping Cart", "docstatus": 0},
			["name", "modified"],
			order_by="modified desc",
			as_dict=True,
		)
	if not meta:
		return None

	return cached_checkout_response(
		meta.name,
		str(meta.modified),
		lambda: checkout.get_checkout_state(frappe.get_doc("Quotation", meta.name)),
		endpoint="commera.api.storefront.checkout.get",
	)


@rate_limited_guest_api("POST", limit=100, seconds=60 * 60)
def set_addresses(
	billing_address: dict | str,
	shipping_address: dict | str | None = None,
	email: str | None = None,
) -> CheckoutState:
	return checkout.set_addresses(
		get_address(billing_address),
		get_address(shipping_address) if shipping_address else None,
		email,
	)


def get_address(address: dict | str) -> dict | str:
	if isinstance(address, str) and address.lstrip().startswith("{"):
		address = frappe.parse_json(address)
	if not isinstance(address, dict | str):
		frappe.throw(_("Send an address as an object or as the name of a saved address."))
	return address


@rate_limited_guest_api("GET", limit=300, seconds=60 * 60)
def list_pickup_locations() -> list[PickupLocation]:
	from commera.storefront_cache import cached_guest_api

	return cached_guest_api(
		"checkout.list_pickup_locations",
		(),
		("shop", "stock"),
		checkout.list_pickup_locations,
		endpoint="commera.api.storefront.checkout.list_pickup_locations",
		ttl=180,
		include_locale=False,
	)


@rate_limited_guest_api("POST", limit=100, seconds=60 * 60)
def set_store_pickup(warehouse: str, email: str | None = None) -> CheckoutState:
	return checkout.set_store_pickup(cstr(warehouse), email)


@rate_limited_guest_api("GET", limit=300, seconds=60 * 60)
def list_shipping_options() -> ShippingOptions:
	return checkout.list_shipping_options()


@rate_limited_guest_api("POST", limit=100, seconds=60 * 60)
def set_shipping_option(option_id: str | None = None) -> CheckoutState:
	return checkout.set_shipping_option(cstr(option_id) or None)


@rate_limited_guest_api("GET", limit=1200, seconds=60 * 60)
def list_payment_methods() -> list[PaymentMethod]:
	from commera.guest import get_guest_cart_key, is_guest
	from commera.storefront_cache import cached_guest_api

	if is_guest() and not get_guest_cart_key():
		return cached_guest_api(
			"checkout.list_payment_methods",
			(),
			("shop",),
			checkout.list_payment_methods,
			endpoint="commera.api.storefront.checkout.list_payment_methods",
			ttl=180,
		)
	return checkout.list_payment_methods()


@rate_limited_guest_api("POST", limit=100, seconds=60 * 60)
def start_payment(
	payment_method: str, expected_total: float | None = None, expected_version: str | None = None
) -> PaymentSession:
	return checkout.start_payment(
		cstr(payment_method),
		None if expected_total in (None, "") else flt(expected_total),
		cstr(expected_version) or None,
	)


@rate_limited_guest_api("POST", limit=100, seconds=60 * 60)
def complete(reference_id: str | None = None) -> CheckoutResult:
	return checkout.complete(cstr(reference_id) or None)
