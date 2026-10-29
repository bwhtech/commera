import click
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

	if OLD_APP not in frappe.get_installed_apps():
		return

	if frappe.db.exists("Module Def", OLD_MODULE):
		# Every Link to the module: DocType, Custom Field, Property Setter and the rest.
		update_link_field_values(get_link_fields("Module Def"), OLD_MODULE, MODULE, "Module Def")
		# Not delete_doc: Module Def.on_trash removes the module folder in developer mode.
		frappe.db.delete("Module Def", OLD_MODULE)

	# Not uninstall-app: that drops the tables this patch keeps.
	remove_from_installed_apps(OLD_APP)
	# Hooks stay site-cached past the removal; the rest of this migrate must not see bwh_shipping's.
	frappe.clear_cache()
	# The module map was built at connect; without a rebuild the model sync skips the Shipping module.
	frappe.setup_module_map(include_all_apps=False)
	click.secho(
		"Shipping is part of Commera now. Run `bench remove-app bwh_shipping` once every site has migrated.",
		fg="yellow",
	)
