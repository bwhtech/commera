import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cstr

from commera.sdk import account
from commera.sdk.types import CustomerAddress, CustomerProfile, ShopperOrder, ShopperOrderPage


# Signed-in shoppers only: the storefront server sends their OAuth access token as a Bearer header.
@frappe.whitelist(methods=["GET"])
@rate_limit(limit=300, seconds=60, user_based=True)
def get_profile() -> CustomerProfile:
	return account.get_profile()


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60 * 60, user_based=True)
def update_profile(
	first_name: str, last_name: str | None = None, phone: str | None = None
) -> CustomerProfile:
	return account.update_profile(first_name, last_name, phone)


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=300, seconds=60, user_based=True)
def list_addresses() -> list[CustomerAddress]:
	return account.list_addresses()


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60 * 60, user_based=True)
def save_address(address: dict | str) -> CustomerAddress:
	"""With `name`, updates that address; without it, adds one."""
	address = frappe.parse_json(address)
	if not isinstance(address, dict):
		frappe.throw(_("Send the address as an object."))
	return account.save_address(address)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=60, seconds=60 * 60, user_based=True)
def delete_address(name: str) -> None:
	account.delete_address(cstr(name))


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=300, seconds=60, user_based=True)
def list_orders(page: int = 1, page_size: int = 10) -> ShopperOrderPage:
	return account.list_orders(page, page_size)


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=300, seconds=60, user_based=True)
def get_order(name: str) -> ShopperOrder:
	return account.get_order(cstr(name))
