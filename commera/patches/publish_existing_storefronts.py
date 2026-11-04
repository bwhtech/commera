import frappe


def execute():
	"""Stores that were already open stay open: only a store set up after this change starts private."""
	if frappe.is_setup_complete():
		frappe.db.set_single_value("Commera Settings", "storefront_published", 1)
