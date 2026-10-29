import frappe
from frappe import _
from frappe.utils.data import cstr, flt

from commera.api.payments import (
	CheckoutPriceChangedError,
	cart_write_lock,
	generate_quotation_for_cart,
	get_checkout_cart,
	get_checkout_payment_methods,
	get_cod_total_key,
	get_open_gateway_payment_request,
	get_quotation_for_cart,
	open_checkout,
	resolve_checkout_payment,
	save_guest_cart,
	save_quotation_address,
	validate_cart_is_not_in_checkout,
)
from commera.api.shipping import get_cart_shipping_options, get_checkout_summary, save_delivery_option
from commera.core import COD_PAYMENT_MODE, is_cod, is_shoppers_address
from commera.guest import is_guest, validate_guest_checkout_enabled
from commera.sdk.cart import get_open_cart_quotation
from commera.sdk.types import (
	CheckoutResult,
	CheckoutState,
	PaymentMethod,
	PaymentSession,
	ShippingOption,
	ShippingOptions,
)
from commera.www.cart.checkout import cart_needs_refresh

__all__ = [
	"complete",
	"list_payment_methods",
	"list_shipping_options",
	"set_addresses",
	"set_shipping_option",
	"set_store_pickup",
	"start_payment",
]

ADDRESS_FIELDS = (
	"address_title",
	"address_line1",
	"address_line2",
	"city",
	"state",
	"pincode",
	"country",
	"phone",
)
CHECKOUT_ADDRESS_KEYS = {
	"address_line1": "full_address",
	"address_line2": "landmark",
	"city": "city",
	"state": "state",
	"pincode": "po_box",
	"country": "country",
	"phone": "phone_number",
	"first_name": "first_name",
	"last_name": "last_name",
}
NO_OPTIONS_REASONS = ("store_pickup", "connector_missing", "address_missing", "unavailable")


def set_addresses(
	billing_address: dict | str, shipping_address: dict | str | None = None, email: str | None = None
) -> CheckoutState:
	email = get_checkout_email(email)
	address = {
		"is_store_pickup": False,
		"billing_address": get_address_input(billing_address, email),
		"shipping_same_as_billing": shipping_address is None,
	}
	if shipping_address is not None:
		address["shipping_address"] = get_address_input(shipping_address, email)
	return save_checkout_address(address, email)


def set_store_pickup(warehouse: str, email: str | None = None) -> CheckoutState:
	email = get_checkout_email(email)
	address = {
		"is_store_pickup": True,
		"store_pickup_warehouse": cstr(warehouse),
		"billing_address": {"email": email},
	}
	return save_checkout_address(address, email)


def save_checkout_address(address: dict, email: str | None) -> CheckoutState:
	quotation = save_guest_cart({}, email) if is_guest() else generate_quotation_for_cart({})
	with cart_write_lock(quotation):
		save_quotation_address(quotation, address)
		return get_checkout_state(quotation)


def get_checkout_email(email: str | None) -> str | None:
	return (cstr(email).strip() or None) if is_guest() else frappe.session.user


def get_address_input(address: dict | str, email: str | None) -> dict:
	if isinstance(address, str):
		if not is_guest() and not is_shoppers_address(address):
			raise frappe.DoesNotExistError(_("Address {0} not found").format(address))
		return {"is_saved": True, "address_id": address, "email": email}
	if not isinstance(address, dict):
		frappe.throw(_("Send an address as an object or as the name of a saved address."))
	return {
		**{checkout_key: address.get(fieldname) for fieldname, checkout_key in CHECKOUT_ADDRESS_KEYS.items()},
		"email": email,
	}


def list_shipping_options() -> ShippingOptions:
	quotation = get_open_checkout()
	if not quotation:
		return {"options": [], "selected": None, "reason": "address_missing"}
	result = get_cart_shipping_options(quotation)
	return {
		"options": [get_shipping_option(option) for option in result["options"]],
		"selected": result.get("selected") or None,
		"reason": next((reason for reason in NO_OPTIONS_REASONS if result.get(reason)), None),
	}


def get_shipping_option(option: dict) -> ShippingOption:
	return {
		"id": option["title"],
		"title": option["title"],
		"description": option.get("description") or None,
		"provider": option.get("provider"),
		"amount": flt(option["amount"]),
		"original_amount": flt(option["original_amount"]) if option.get("original_amount") else None,
		"is_free": not flt(option["amount"]),
		"min_delivery_date": option.get("min_delivery_date"),
		"max_delivery_date": option.get("max_delivery_date"),
		"phone_required": bool(option.get("phone_required")),
	}


def set_shipping_option(option_id: str | None) -> CheckoutState:
	quotation = get_checkout_quotation()
	with cart_write_lock(quotation):
		validate_cart_is_not_in_checkout(quotation.name)
		if cart_needs_refresh(quotation):
			get_quotation_for_cart(get_checkout_cart({}), quotation)
	save_delivery_option(quotation, cstr(option_id) or None)
	return get_checkout_state(quotation)


def list_payment_methods() -> list[PaymentMethod]:
	return [
		{
			"id": payment_method,
			"title": _("Cash on Delivery") if is_cod(payment_method) else _(payment_method),
			"is_cash_on_delivery": is_cod(payment_method),
		}
		for payment_method in get_checkout_payment_methods(get_open_checkout())
	]


def start_payment(payment_method: str, expected_total: float | None = None) -> PaymentSession:
	quotation = get_checkout_quotation()
	with cart_write_lock(quotation):
		if cart_needs_refresh(quotation):
			frappe.throw(
				_("Your cart has changed. Please choose your delivery again before placing your order."),
				title=_("Cart Changed"),
				exc=CheckoutPriceChangedError,
			)
		session = open_checkout(
			quotation, cstr(payment_method), quotation.custom_delivery_option, expected_total
		)
	return {"redirect_url": session["order_url"], "reference_id": quotation.name}


def complete(reference_id: str | None = None) -> CheckoutResult:
	reference_id = cstr(reference_id) or get_checkout_quotation().name
	result = resolve_checkout_payment(reference_id, get_payment_mode(reference_id))
	order = None
	if result.get("order_link"):
		order = {
			"name": result["order_name"],
			"link": result["order_link"],
			"grand_total": flt(result["grand_total"]),
			"currency": result["currency"],
		}
	return {"status": result["status"], "order": order}


def get_payment_mode(reference_id: str) -> str | None:
	if frappe.cache.get_value(get_cod_total_key(reference_id)) is None:
		return None
	return None if get_open_gateway_payment_request(reference_id) else COD_PAYMENT_MODE


def get_open_checkout():
	if is_guest():
		validate_guest_checkout_enabled()
	return get_open_cart_quotation()


def get_checkout_quotation():
	quotation = get_open_checkout()
	if not quotation:
		frappe.throw(_("Enter your address first."), frappe.DoesNotExistError)
	return quotation


def get_checkout_state(quotation) -> CheckoutState:
	address_names = [name for name in (quotation.customer_address, quotation.shipping_address_name) if name]
	addresses = {}
	if address_names:
		addresses = {
			address.name: address
			for address in frappe.get_all(
				"Address", filters={"name": ("in", address_names)}, fields=["name", *ADDRESS_FIELDS]
			)
		}
	return {
		"cart": quotation.name,
		"email": quotation.contact_email,
		"billing_address": addresses.get(quotation.customer_address),
		"shipping_address": addresses.get(quotation.shipping_address_name),
		"is_store_pickup": bool(quotation.custom_is_store_pickup),
		"store": quotation.custom_store or None,
		"shipping_option": quotation.custom_delivery_option or None,
		"summary": get_checkout_summary(quotation),
	}
