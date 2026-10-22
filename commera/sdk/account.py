import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count
from frappe.utils.data import cint, cstr
from pypika import Order

from commera.api.signup import validate_user_names
from commera.api.users import delete_user_address
from commera.core import get_address_docs, get_party
from commera.guest import is_guest
from commera.sdk.orders import read_order_results
from commera.sdk.types import CustomerAddress, CustomerProfile, ShopperOrder, ShopperOrderPage

__all__ = [
	"delete_address",
	"get_order",
	"get_profile",
	"list_addresses",
	"list_orders",
	"save_address",
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
		doc.save()
	else:
		party = get_party(get_shopper())
		doc = frappe.get_doc({"doctype": "Address", **values})
		doc.address_title = doc.address_title or get_profile()["full_name"]
		doc.append("links", {"link_doctype": party.doctype, "link_name": party.name})
		doc.insert()
	return get_address_result(doc)


def get_own_address(name: str):
	shopper = get_shopper()
	if frappe.db.get_value("Address", name, "owner") != shopper:
		raise frappe.DoesNotExistError(_("Address {0} not found").format(name))
	return frappe.get_doc("Address", name)


def delete_address(name: str) -> None:
	get_own_address(name)
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
	condition = get_shopper_order_condition()
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


def get_order(name: str) -> ShopperOrder:
	sales_order = DocType("Sales Order")
	is_shoppers = (
		frappe.qb.from_(sales_order)
		.select(sales_order.name)
		.where((sales_order.name == name) & get_shopper_order_condition())
		.run()
	)
	orders = read_order_results([name], ()) if is_shoppers else {}
	if cstr(name) not in orders:
		raise frappe.DoesNotExistError(_("Order {0} not found").format(name))
	return without_staff_fields(orders[cstr(name)])


def get_shopper_order_condition():
	"""Orders the shopper placed, and guest orders with their email: the OTP sign-in proved they own it."""
	shopper = get_shopper()
	sales_order, order_line, cart = DocType("Sales Order"), DocType("Sales Order Item"), DocType("Quotation")
	guest_orders = (
		frappe.qb.from_(order_line)
		.join(cart)
		.on(cart.name == order_line.prevdoc_docname)
		.select(order_line.parent)
		.where((order_line.parenttype == "Sales Order") & (cart.custom_guest_cart_key != ""))
	)
	email = frappe.db.get_value("User", shopper, "email")
	return (sales_order.owner == shopper) | (
		(sales_order.contact_email == email) & sales_order.name.isin(guest_orders)
	)


def without_staff_fields(order) -> ShopperOrder:
	return {key: value for key, value in order.items() if key != "tags"}
