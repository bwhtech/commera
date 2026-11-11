import frappe
from frappe import _

from commera.api.shipping import get_charge_summary
from commera.localization import url
from commera.order_access import OWNER_ACCESS, get_order_access
from commera.www.account.orders.index import get_orders_list, get_return_state

no_cache = True


def get_context(context):
	order_id = frappe.form_dict.get("order_id")
	if not order_id:
		frappe.redirect(url("/account/orders"))
	order_access = get_order_access(order_id, frappe.form_dict.get("key"))
	if not order_access:
		if frappe.session.user == "Guest":
			raise frappe.PermissionError
		frappe.redirect(url("/account/orders"))
	_, order_details = get_orders_list([order_id], owned_only=order_access == OWNER_ACCESS)
	if not order_details:
		frappe.redirect(url("/account/orders"))
	context.order = order_details[0]
	context.order_summary = get_charge_summary(frappe.get_cached_doc("Sales Order", order_id))
	# Rendered with the page, so Cancel and Return never show before it is known what was returned.
	context.return_state = (
		get_return_state(frappe.get_doc("Sales Order", order_id)) if order_access == OWNER_ACCESS else None
	)
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
			"label": _("My Account"),
			"href": url("/account/"),
		},
		{
			"label": _("Orders"),
			"href": url("/account/orders"),
		},
		{
			"label": order_id,
			"href": "#",
		},
	]
