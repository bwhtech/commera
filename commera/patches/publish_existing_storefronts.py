import frappe


def execute():
	if frappe.is_setup_complete():
		frappe.db.set_single_value("Commera Settings", "storefront_published", 1)
