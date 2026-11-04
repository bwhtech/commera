import frappe


def execute():
	"""Stores that already finished setup skip the first-run onboarding."""
	if frappe.is_setup_complete():
		frappe.db.set_single_value("Commera Settings", "onboarding_completed", 1)
