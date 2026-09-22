import frappe

MODULE_NAME = "Shop Themes"
LEGACY_APP = "ls_shop"
CURRENT_APP = "commera"


def execute():
	"""Move the shared theme module to Commera after the app rename."""
	owner = frappe.db.get_value("Module Def", MODULE_NAME, "app_name")
	if owner != LEGACY_APP:
		return

	frappe.db.set_value("Module Def", MODULE_NAME, "app_name", CURRENT_APP, update_modified=False)
	frappe.clear_document_cache("Module Def", MODULE_NAME)
	frappe.cache.delete_value("app_modules")
	frappe.client_cache.delete_value("installed_app_modules")
	frappe.setup_module_map()
