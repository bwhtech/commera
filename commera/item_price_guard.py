"""ERPNext's "Auto insert Item Price if missing" adds a price from a transaction line's rate. A cart
line must not set the store's prices: a regular-only line or a discounted rate would put it on sale."""

import functools
from contextlib import contextmanager

import frappe
from erpnext.stock import get_item_details

CART_ORDER_TYPE = "Shopping Cart"
SKIP_FLAG = "commera_skip_auto_item_price"

_installed = False


def install_guard():
	"""before_request and before_job: wrap ERPNext's insert once per process, before any pricing."""
	global _installed
	if _installed:
		return
	insert_item_price = get_item_details.insert_item_price
	if not getattr(insert_item_price, "skips_cart_lines", False):
		get_item_details.insert_item_price = skip_cart_lines(insert_item_price)
	_installed = True


@contextmanager
def skip_auto_item_price():
	"""Around Commera's own cart pricing and order placement: no line sets a store price."""
	install_guard()
	previous = frappe.flags.get(SKIP_FLAG)
	frappe.flags[SKIP_FLAG] = True
	try:
		yield
	finally:
		frappe.flags[SKIP_FLAG] = previous


def skip_cart_lines(insert_item_price):
	@functools.wraps(insert_item_price)
	def insert_unless_cart_line(ctx):
		if not frappe.flags.get(SKIP_FLAG) and not is_cart_line(ctx):
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
