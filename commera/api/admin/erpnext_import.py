# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils.data import cint

from commera import erpnext_import
from commera.commera_ecommerce.doctype.commera_settings.editor_input import parse_list

PAGE_LENGTH = 50


@frappe.whitelist()
def get_erpnext_import_preview(search: str | None = None, start: int = 0, page_length: int = PAGE_LENGTH):
	frappe.has_permission("Item", "create", throw=True)
	return erpnext_import.get_preview(search, cint(start), cint(page_length) or PAGE_LENGTH)


@frappe.whitelist(methods=["POST"])
def start_erpnext_import(item_codes: list | str | None = None):
	frappe.has_permission("Item", "create", throw=True)
	erpnext_import.check_import_settings()
	if item_codes is not None:
		item_codes = parse_list(item_codes)
		if not item_codes:
			frappe.throw(_("Pick at least one item to import."))
	return erpnext_import.queue_import(item_codes)


@frappe.whitelist()
def get_erpnext_import_status(job_id: str):
	frappe.has_permission("Item", "create", throw=True)
	return erpnext_import.get_status(job_id)


@frappe.whitelist(methods=["POST"])
def publish_imported_products(log: str):
	frappe.has_permission("Item", "create", throw=True)
	return erpnext_import.publish_imported_products(log)
