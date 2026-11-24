import frappe

from commera.patches.rename_pixio_theme_to_summer import rename_if_pending


def execute():
	frappe.flags.in_import = True
	try:
		rename_if_pending("DocType", "Commera Starter Settings", "Commera Standard Settings")
		rename_if_pending("Shop Theme", "Commera Starter", "Commera Standard")
	finally:
		frappe.flags.in_import = False
