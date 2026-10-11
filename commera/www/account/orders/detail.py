import frappe

from commera.order_access import OWNER_ACCESS, get_order_access
from commera.www.account.orders.index import get_orders_list

no_cache = True


def get_context(context):
	order_id = frappe.form_dict.get("order_id")
	if not order_id:
		frappe.redirect(f"/{frappe.local.lang}/account/orders")
	order_access = get_order_access(order_id, frappe.form_dict.get("key"))
	if not order_access:
		if frappe.session.user == "Guest":
			raise frappe.PermissionError
		frappe.redirect(f"/{frappe.local.lang}/account/orders")
	_, order_details = get_orders_list([order_id], owned_only=order_access == OWNER_ACCESS)
	if not order_details:
		frappe.redirect(f"/{frappe.local.lang}/account/orders")
	context.order = order_details[0]
	context.order_access = order_access
	context.order_key = frappe.form_dict.get("key") if order_access != OWNER_ACCESS else None
	context.return_period = frappe.get_cached_value("Commera Settings", "Commera Settings", "return_period")
	return_reasons = frappe.get_cached_value("Commera Settings", "Commera Settings", "reason_for_return")
	context.return_reasons = [
		{"name": return_reason.name, "display_name": return_reason.display_name}
		for return_reason in return_reasons
	]
	context.breadcrumbs = get_breadcrumbs(order_id)


def get_breadcrumbs(order_id):
	return [
		{
			"label": "My Account",
			"href": f"/{frappe.local.lang}/account/",
		},
		{
			"label": "Orders",
			"href": f"/{frappe.local.lang}/account/orders",
		},
		{
			"label": order_id,
			"href": "#",
		},
	]
