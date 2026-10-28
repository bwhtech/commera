import frappe
from frappe.installer import remove_from_installed_apps
from frappe.model.rename_doc import get_link_fields, update_link_field_values

OLD_MODULE = "BWH Shipping"
MODULE = "Shipping"
OLD_APP = "bwh_shipping"


def execute():
	"""File the bwh_shipping doctypes and customizations under Commera's Shipping module, then drop the app.
	Must stay pre-model-sync, so the sync reads the doctypes from Commera. No table or record moves."""
	# Migrate's sync_module_defs usually adds the module from modules.txt before patches run.
	if not frappe.db.exists("Module Def", MODULE):
		frappe.get_doc({"doctype": "Module Def", "module_name": MODULE, "app_name": "commera"}).insert(
			ignore_permissions=True
		)

	if frappe.db.exists("Module Def", OLD_MODULE):
		# Every Link to the module: DocType, Custom Field, Property Setter and the rest.
		update_link_field_values(get_link_fields("Module Def"), OLD_MODULE, MODULE, "Module Def")
		# Not delete_doc: Module Def.on_trash removes the module folder in developer mode.
		frappe.db.delete("Module Def", OLD_MODULE)

	# Not uninstall-app: that drops the tables this patch keeps.
	remove_from_installed_apps(OLD_APP)

	frappe.cache.delete_value("app_modules")
	frappe.client_cache.delete_value("installed_app_modules")
	frappe.setup_module_map()
