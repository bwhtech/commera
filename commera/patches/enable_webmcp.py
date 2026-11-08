import frappe


def execute():
	frappe.db.set_single_value("Commera Settings", "enable_webmcp", 1)
