import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cstr, flt

from commera.sdk import checkout
from commera.sdk.types import (
	CheckoutResult,
	CheckoutState,
	PaymentMethod,
	PaymentSession,
	PickupLocation,
	ShippingOptions,
)


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=1200, seconds=60 * 60)
def get() -> CheckoutState | None:
	return checkout.get()


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=100, seconds=60 * 60)
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


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=300, seconds=60 * 60)
def list_pickup_locations() -> list[PickupLocation]:
	return checkout.list_pickup_locations()


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=100, seconds=60 * 60)
def set_store_pickup(warehouse: str, email: str | None = None) -> CheckoutState:
	return checkout.set_store_pickup(cstr(warehouse), email)


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=300, seconds=60 * 60)
def list_shipping_options() -> ShippingOptions:
	return checkout.list_shipping_options()


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=100, seconds=60 * 60)
def set_shipping_option(option_id: str | None = None) -> CheckoutState:
	return checkout.set_shipping_option(cstr(option_id) or None)


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=1200, seconds=60 * 60)
def list_payment_methods() -> list[PaymentMethod]:
	return checkout.list_payment_methods()


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=100, seconds=60 * 60)
def start_payment(
	payment_method: str, expected_total: float | None = None, expected_version: str | None = None
) -> PaymentSession:
	return checkout.start_payment(
		cstr(payment_method),
		None if expected_total in (None, "") else flt(expected_total),
		cstr(expected_version) or None,
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=100, seconds=60 * 60)
def complete(reference_id: str | None = None) -> CheckoutResult:
	return checkout.complete(cstr(reference_id) or None)
