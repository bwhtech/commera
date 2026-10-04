import frappe
from commera.sdk import STORE_ORDER_TYPE
from frappe.utils import today


@frappe.whitelist()
def get_summary() -> dict:
	frappe.has_permission("Sales Order", "read", throw=True)
	return {
		"orders_today": frappe.db.count(
			"Sales Order",
			{"order_type": STORE_ORDER_TYPE, "transaction_date": today(), "docstatus": ("<", 2)},
		)
	}
