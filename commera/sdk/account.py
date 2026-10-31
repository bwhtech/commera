import importlib
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count
from frappe.utils.data import cint, cstr
from pypika import Order

from commera.api.order_link import email_order_link
from commera.api.orders import cancel_order as cancel_sales_order
from commera.api.payments import add_customer_address
from commera.api.shipping import read_order_tracking
from commera.api.signup import validate_user_names
from commera.api.users import delete_user_address
from commera.core import get_address_docs, get_party, is_shoppers_address
from commera.guest import is_guest
from commera.order_access import (
	FULL_ACCESS,
	LIMITED_ACCESS,
	OWNER_ACCESS,
	get_order_access,
	get_shopper_order_condition,
)
from commera.sdk.orders import read_order_results
from commera.sdk.types import (
	CustomerAddress,
	CustomerProfile,
	OrderTracking,
	ReturnOptions,
	ShopperOrder,
	ShopperOrderDetail,
	ShopperOrderPage,
)
from commera.utils import get_return_deadline, validate_document_access

__all__ = [
	"cancel_order",
	"delete_address",
	"get_invoice_url",
	"get_order",
	"get_order_tracking",
	"get_profile",
	"get_return_options",
	"list_addresses",
	"list_orders",
	"request_return",
	"save_address",
	"send_order_link",
	"update_profile",
]

ADDRESS_FIELDS = (
	"address_title",
	"address_type",
	"address_line1",
	"address_line2",
	"city",
	"state",
	"pincode",
	"country",
	"phone",
	"email_id",
	"is_primary_address",
	"is_shipping_address",
)
MAX_ORDER_PAGE_SIZE = 50
LIMITED_LINK_HIDDEN_FIELDS = ("shipping_address", "email", "phone", "payment_mode")

return_api = importlib.import_module("commera.api.return")


def get_shopper() -> str:
	if is_guest():
		raise frappe.PermissionError(_("Please sign in."))
	return frappe.session.user


def get_profile() -> CustomerProfile:
	user = frappe.db.get_value(
		"User", get_shopper(), ["email", "first_name", "last_name", "full_name", "mobile_no"], as_dict=True
	)
	return {
		"email": user.email,
		"first_name": user.first_name,
		"last_name": user.last_name,
		"full_name": user.full_name,
		"phone": user.mobile_no,
	}


def update_profile(
	first_name: str, last_name: str | None = None, phone: str | None = None
) -> CustomerProfile:
	"""None leaves a field as it is. The User doc validates the phone number."""
	user = frappe.get_doc("User", get_shopper())
	values = {"first_name": first_name, "last_name": last_name, "mobile_no": phone}
	user.update({fieldname: cstr(value).strip() for fieldname, value in values.items() if value is not None})
	validate_user_names(user.first_name, user.last_name)
	user.save()
	return get_profile()


def list_addresses() -> list[CustomerAddress]:
	"""Addresses of the shopper's Customer. Reading never creates the Customer."""
	party = get_party(get_shopper(), create=False)
	return [get_address_result(address) for address in get_address_docs(party)] if party else []


def save_address(address: dict) -> CustomerAddress:
	"""Update the shopper's own address when `name` is set, else add one to their Customer."""
	values = {fieldname: address.get(fieldname) for fieldname in ADDRESS_FIELDS if fieldname in address}
	if name := address.get("name"):
		doc = get_own_address(name)
		doc.update(values)
		# Guest checkouts file addresses the shopper does not own; the Customer link is the ownership check.
		doc.save(ignore_permissions=True)
	else:
		values["address_type"] = values.get("address_type") or "Shipping"
		values["address_title"] = values.get("address_title") or get_profile()["full_name"]
		doc = add_customer_address(get_party(get_shopper()).name, values)
	return get_address_result(doc)


def get_own_address(name: str):
	if not is_shoppers_address(name):
		frappe.throw(_("Address {0} not found").format(name), frappe.DoesNotExistError)
	return frappe.get_doc("Address", name)


def delete_address(name: str) -> None:
	delete_user_address(name)


def get_address_result(address) -> CustomerAddress:
	result = {"name": address.name, **{fieldname: address.get(fieldname) for fieldname in ADDRESS_FIELDS}}
	for fieldname in ("is_primary_address", "is_shipping_address"):
		result[fieldname] = bool(cint(result[fieldname]))
	return result


def list_orders(page: int = 1, page_size: int = 10) -> ShopperOrderPage:
	"""Newest first: the shopper's orders and guest orders placed with their email."""
	page, page_size = max(cint(page), 1), min(max(cint(page_size), 1), MAX_ORDER_PAGE_SIZE)
	sales_order = DocType("Sales Order")
	condition = get_shopper_order_condition(get_shopper())
	total = frappe.qb.from_(sales_order).select(Count("*")).where(condition).run()[0][0]
	names = (
		frappe.qb.from_(sales_order)
		.select(sales_order.name)
		.where(condition)
		.orderby(sales_order.creation, order=Order.desc)
		.limit(page_size)
		.offset((page - 1) * page_size)
		.run(pluck=True)
	)
	orders = read_order_results(names, ())
	return {
		"orders": [without_staff_fields(orders[cstr(name)]) for name in names],
		"total": total,
		"page": page,
		"page_size": page_size,
	}


def get_order(name: str, key: str | None = None) -> ShopperOrderDetail:
	validate_document_access("Sales Order", name, key)
	access = get_order_access(name, key) or FULL_ACCESS
	order = without_staff_fields(read_order_results([name], ())[cstr(name)])
	if access == LIMITED_ACCESS:
		order.update(dict.fromkeys(LIMITED_LINK_HIDDEN_FIELDS))
	return {**order, "access": access}


def get_own_order(name: str) -> str:
	get_shopper()
	if get_order_access(name) != OWNER_ACCESS:
		frappe.throw(_("Order {0} not found").format(name), frappe.DoesNotExistError)
	return cstr(name)


def cancel_order(name: str) -> ShopperOrderDetail:
	cancel_sales_order(get_own_order(name))
	return get_order(name)


def get_return_options(name: str) -> ReturnOptions:
	name = get_own_order(name)
	settings = frappe.get_cached_doc("Commera Settings")
	return_by = get_return_deadline(name, settings.return_period) if settings.return_period else None
	returned = return_api.get_returned_items(name)
	return {
		"can_return": bool(return_by) and frappe.utils.now_datetime() <= return_by,
		"return_by": return_by,
		"reasons": [
			{"name": reason.name, "label": reason.display_name} for reason in settings.reason_for_return
		],
		"returned_items": returned["returned_items"],
		"pending_items": returned["returned_items_in_draft"],
	}


def request_return(name: str, items: list[dict]) -> ReturnOptions:
	return_api.return_items(get_own_order(name), items)
	return get_return_options(name)


def get_invoice_url(name: str) -> str | None:
	invoices = frappe.get_all(
		"Sales Invoice Item",
		filters={"sales_order": get_own_order(name), "docstatus": 1},
		pluck="parent",
		limit=1,
	)
	if not invoices:
		return None
	print_format = frappe.get_cached_value("Commera Settings", "Commera Settings", "print_format")
	query = urlencode({"doctype": "Sales Invoice", "name": invoices[0], "format": print_format or "Standard"})
	return f"/api/method/frappe.utils.print_format.download_pdf?{query}"


def get_order_tracking(name: str, key: str | None = None) -> OrderTracking:
	validate_document_access("Sales Order", name, key)
	return read_order_tracking(cstr(name))


def send_order_link(order_number: str, email: str) -> str:
	return email_order_link(order_number, email)


def without_staff_fields(order) -> ShopperOrder:
	return {key: value for key, value in order.items() if key != "tags"}
