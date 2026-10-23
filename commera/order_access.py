import hmac
from urllib.parse import urlencode

import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Lower
from frappe.utils import add_days, cint, cstr, get_datetime, get_url, now_datetime

OWNER_ACCESS = "owner"
FULL_ACCESS = "full"
LIMITED_ACCESS = "limited"

ORDER_ACCESS_FIELDS = (
	"name",
	"owner",
	"creation",
	"custom_order_access_key",
	"custom_order_access_key_issued_on",
)


def set_order_access_key(sales_order) -> str:
	# Idempotent: the confirmation email can issue the key before checkout does, and both must share one link.
	return sales_order.get("custom_order_access_key") or reset_order_access_key(sales_order)


def reset_order_access_key(sales_order) -> str:
	key = frappe.generate_hash(length=32)
	sales_order.db_set(
		{"custom_order_access_key": key, "custom_order_access_key_issued_on": now_datetime()},
		update_modified=False,
	)
	return key


def get_order_link(sales_order) -> str | None:
	key = sales_order.get("custom_order_access_key")
	if not key:
		return None
	language = "ar" if frappe.local.lang == "ar" else "en"
	query = urlencode({"order_id": sales_order.name, "key": key})
	return get_url(f"/{language}/account/orders/detail?{query}")


def get_order_access(order_name: str | int, key: str | None = None) -> str | None:
	order = frappe.db.get_value("Sales Order", order_name, ORDER_ACCESS_FIELDS, as_dict=True)
	if not order:
		return None
	if is_shoppers_order(order):
		return OWNER_ACCESS
	return get_key_access(order, key)


def is_shoppers_order(order) -> bool:
	user = frappe.session.user
	if user == "Guest":
		return False
	if order.owner == user:
		return True
	sales_order = DocType("Sales Order")
	return bool(
		frappe.qb.from_(sales_order)
		.select(sales_order.name)
		.where((sales_order.name == order.name) & get_shopper_order_condition(user))
		.run()
	)


def get_shopper_order_condition(user: str):
	"""Orders the user placed, and guest-cart orders placed with their email: signing in proved they own it."""
	sales_order = DocType("Sales Order")
	if user == "Guest":
		# Match nothing: `owner == "Guest"` would hand a guest every order a guest session owns.
		return sales_order.name.isnull()
	order_line, cart = DocType("Sales Order Item"), DocType("Quotation")
	guest_orders = (
		frappe.qb.from_(order_line)
		.join(cart)
		.on(cart.name == order_line.prevdoc_docname)
		.select(order_line.parent)
		.where((order_line.parenttype == "Sales Order") & (cart.custom_guest_cart_key != ""))
	)
	email = cstr(frappe.db.get_value("User", user, "email")).lower()
	# Checkout lowercases contact_email, but User.email keeps the case the shopper signed up with.
	return (sales_order.owner == user) | (
		(Lower(sales_order.contact_email) == email) & sales_order.name.isin(guest_orders)
	)


def get_key_access(order, key: str | None) -> str | None:
	stored_key = order.get("custom_order_access_key")
	if not key or not stored_key:
		return None
	if not hmac.compare_digest(cstr(key).encode(), stored_key.encode()):
		return None
	return FULL_ACCESS if is_within_link_window(order) else LIMITED_ACCESS


def is_within_link_window(order) -> bool:
	link_days = cint(frappe.get_cached_value("Commera Settings", "Commera Settings", "guest_order_link_days"))
	if not link_days:
		return True
	issued_on = order.get("custom_order_access_key_issued_on") or order.get("creation")
	return now_datetime() <= add_days(get_datetime(issued_on), link_days)
