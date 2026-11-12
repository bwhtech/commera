"""ERPNext's "Auto insert Item Price if missing" adds a price from a transaction line's rate. A cart
line must not set the store's prices: a regular-only line or a discounted rate would put it on sale."""

import functools
from contextlib import contextmanager

import frappe

# ERPNext offers no hook to skip its auto Item Price insert/update; the wrapper is the only full guard.
# nosemgrep: frappe-semgrep-rules.rules.frappe-monkey-patching-not-allowed
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
		if not frappe.get_cached_doc("Stock Settings").auto_insert_price_list_rate_if_missing:
			return
		if not frappe.flags.get(SKIP_FLAG) and not is_cart_line(ctx):
			insert_item_price(ctx)

	insert_unless_cart_line.skips_cart_lines = True
	return insert_unless_cart_line


def is_cart_line(ctx) -> bool:
	"""A line of a cart quotation or order, or of any document ERPNext maps from a cart order."""
	if ctx.get("order_type"):
		return ctx.order_type == CART_ORDER_TYPE
	return source_order_type(ctx) == CART_ORDER_TYPE


def source_order_type(ctx) -> str | None:
	# Every ERPNext mapper from a Sales Order (Delivery Note, Sales Invoice, Pick List, returns, and
	# their chains) keeps `so_detail`, ERPNext's own join field for delivered and billed qty.
	if not ctx.get("so_detail"):
		return None
	cache = getattr(frappe.local, "commera_source_order_types", None)
	if cache is None:
		cache = frappe.local.commera_source_order_types = {}
	if ctx.so_detail not in cache:
		# Resolve every row of this order once, including negative results, for this request only.
		rows = frappe.db.sql(
			"""select item.name, orders.order_type
			from `tabSales Order Item` item
			join `tabSales Order` orders on orders.name = item.parent
			where item.parent = (
				select parent from `tabSales Order Item` where name = %s
			)""",
			(ctx.so_detail,),
		)
		cache[ctx.so_detail] = None
		cache.update(rows)
	return cache[ctx.so_detail]


def refuse_cart_quotation_invoice(doc, method, source, table_maps):
	# The direct mapper drops quotation provenance. Invoice the cart's Sales Order instead.
	if source.doctype == "Quotation" and source.order_type == CART_ORDER_TYPE:
		frappe.throw(
			frappe._(
				"Cannot invoice a Shopping Cart Quotation directly. Create the Sales Invoice from its Sales Order."
			)
		)
