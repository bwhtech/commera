import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cstr

from commera.sdk import account
from commera.sdk.types import OrderTracking, ReturnOptions, ShopperOrderDetail


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60 * 60, user_based=True)
def cancel_order(name: str) -> ShopperOrderDetail:
	return account.cancel_order(cstr(name))


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=300, seconds=60, user_based=True)
def get_return_options(name: str) -> ReturnOptions:
	return account.get_return_options(cstr(name))


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60 * 60, user_based=True)
def request_return(name: str, items: list | str) -> ReturnOptions:
	items = frappe.parse_json(items)
	if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
		frappe.throw(_("Items to return must be a list of objects."))
	return account.request_return(cstr(name), items)


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=300, seconds=60, user_based=True)
def get_invoice_url(name: str) -> str | None:
	return account.get_invoice_url(cstr(name))


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=120, seconds=60 * 60)
def get_order_tracking(name: str, key: str | None = None) -> OrderTracking:
	return account.get_order_tracking(cstr(name), key)


@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=10, seconds=60 * 60)
def send_order_link(order_number: str, email: str) -> str:
	return account.send_order_link(order_number, email)
