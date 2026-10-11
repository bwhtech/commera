no_cache = True

import frappe

from commera.utils import get_login_url_for_current_page
from commera.www.account.orders.index import get_orders_list


def get_context(context):
	context.no_cache = 1
	# A guest checkout confirms from its cart cookie; the sign-in link only rescues a shopper whose session lapsed.
	if frappe.session.user == "Guest":
		context.login_url = get_login_url_for_current_page()
		return context

	context.order = get_owned_order(frappe.form_dict.get("order_id"))
	return context


def get_owned_order(order_id):
	if not order_id:
		return None
	_, orders = get_orders_list([order_id])
	return orders[0] if orders else None
