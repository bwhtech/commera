"""ERPNext's "Auto insert Item Price if missing" adds a price from a transaction line's rate. A cart
line must not set the store's prices: a regular-only line or a discounted rate would put it on sale."""

import functools

import frappe
from erpnext.stock import get_item_details

CART_ORDER_TYPE = "Shopping Cart"


def guard_item_price_inserts(doc, method=None):
	"""Before validate, where ERPNext prices the lines. Wraps its insert once per process; the
	wrapper skips cart lines and leaves every rate as it is."""
	insert_item_price = get_item_details.insert_item_price
	if not getattr(insert_item_price, "skips_cart_lines", False):
		get_item_details.insert_item_price = skip_cart_lines(insert_item_price)


def skip_cart_lines(insert_item_price):
	@functools.wraps(insert_item_price)
	def insert_unless_cart_line(ctx):
		if not is_cart_line(ctx):
			insert_item_price(ctx)

	insert_unless_cart_line.skips_cart_lines = True
	return insert_unless_cart_line


def is_cart_line(ctx) -> bool:
	"""A line of a cart quotation or order, or of an invoice billed from a cart order."""
	if ctx.get("order_type"):
		return ctx.order_type == CART_ORDER_TYPE
	sales_order = ctx.get("sales_order")
	return bool(sales_order) and (
		frappe.db.get_value("Sales Order", sales_order, "order_type") == CART_ORDER_TYPE
	)
