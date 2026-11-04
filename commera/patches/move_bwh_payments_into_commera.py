import click
import frappe
from frappe.installer import remove_from_installed_apps
from frappe.model.rename_doc import get_link_fields, update_link_field_values

OLD_MODULE = "BWH Payments"
MODULE = "Payment Gateways"
OLD_APP = "bwh_payments"


def execute():
	if not frappe.db.exists("Module Def", MODULE):
		frappe.get_doc({"doctype": "Module Def", "module_name": MODULE, "app_name": "commera"}).insert(
			ignore_permissions=True
		)

	has_old_module = frappe.db.exists("Module Def", OLD_MODULE)
	has_old_app = OLD_APP in frappe.get_installed_apps()
	if not (has_old_module or has_old_app):
		return

	if has_old_module:
		update_link_field_values(get_link_fields("Module Def"), OLD_MODULE, MODULE, "Module Def")
		frappe.db.delete("Module Def", OLD_MODULE)
	if has_old_app:
		remove_from_installed_apps(OLD_APP)
	frappe.clear_cache()
	frappe.setup_module_map(include_all_apps=False)
	click.secho(
		"Payments are part of Commera now. Run `bench remove-app bwh_payments` once every site has migrated.",
		fg="yellow",
	)
