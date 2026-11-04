import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count

from commera.order_access import get_shopper_order_condition
from commera.www.account import dashboard
from commera.www.account.orders.index import get_orders_list

# What update_sales_order_ecommerce_status assigns short of Delivered, Cancelled and Returned.
OPEN_ORDER_STATUSES = ("Waiting for Approval", "Order Received", "Preparing for Shipment", "Shipped")

RECENT_ORDER_COUNT = 5


def get_context(context):
	dashboard.get_context(context)
	context.total_order_count, context.recent_orders = get_orders_list(page_length=RECENT_ORDER_COUNT)
	sales_order = DocType("Sales Order")
	context.open_order_count = (
		frappe.qb.from_(sales_order)
		.select(Count("*"))
		.where(get_shopper_order_condition(frappe.session.user))
		.where(sales_order.custom_ecommerce_status.isin(OPEN_ORDER_STATUSES))
		.run()[0][0]
	)
	return context
