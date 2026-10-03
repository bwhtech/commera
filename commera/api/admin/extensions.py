# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from commera.api.admin.docfields import build_field_groups, get_editable_docfields, get_missing_fields
from commera.api.admin.settings import coerce_field_value
from commera.extensions.places import PLACES, get_record_place_prefix
from commera.extensions.registry import (
	get_registry,
	get_registry_entry,
	get_whitelisted_method,
	has_required_access,
	passes_condition,
	resolve_record_extensions,
)


@frappe.whitelist()
def get_record_extensions(doctype: str, name: str | int) -> dict:
	place_prefix = get_record_place_prefix(doctype)
	if not place_prefix:
		frappe.throw(_("Apps can't extend {0} records").format(doctype))

	frappe.has_permission(doctype, "read", doc=name, throw=True)
	return {"keys": resolve_record_extensions(place_prefix, name, frappe.session.user)}


@frappe.whitelist(methods=["POST"])
def run_record_action(key: str, name: str | int) -> dict:
	entry = get_registry_entry(key)
	if not entry or not entry["method"]:
		frappe.throw(_("App action {0} not found").format(key), frappe.DoesNotExistError)
	if entry.get("error"):
		frappe.throw(entry["error"])

	doctype = PLACES[entry["place"]]["doctype"]
	frappe.has_permission(doctype, "read", doc=name, throw=True)
	method = get_whitelisted_method(entry["app"], entry["method"])
	if not (
		method and has_required_access(entry, frappe.session.user) and passes_condition(entry, doctype, name)
	):
		frappe.throw(_("{0} isn't available for {1}").format(entry["label"], name), frappe.PermissionError)

	message = method(name=name)
	return {"message": message if isinstance(message, str) else None}


@frappe.whitelist()
def get_app_settings(app: str) -> dict:
	doctype = get_app_settings_doctype(app)
	frappe.has_permission(doctype, "read", throw=True)

	groups = build_field_groups(doctype, frappe.get_cached_doc(doctype))
	return {
		"doctype": doctype,
		"groups": groups,
		"values": {field["fieldname"]: field["value"] for group in groups for field in group["fields"]},
	}


@frappe.whitelist(methods=["POST"])
def save_app_setting(app: str, **fields):
	doctype = get_app_settings_doctype(app)
	frappe.has_permission(doctype, "write", throw=True)

	docfields = {docfield.fieldname: docfield for _group_label, docfield in get_editable_docfields(doctype)}
	unknown = set(fields) - set(docfields)
	if unknown:
		frappe.throw(_("{0} has no field {1}").format(doctype, ", ".join(sorted(unknown))))

	# A blank secret keeps the stored one; only an explicit null clears it.
	changed = {
		fieldname: value
		for fieldname, value in fields.items()
		if not (docfields[fieldname].fieldtype == "Password" and value == "")
	}
	settings = frappe.get_doc(doctype)
	if changed:
		for fieldname, value in changed.items():
			settings.set(fieldname, coerce_field_value(docfields[fieldname].fieldtype, value))

		cleared = [fieldname for fieldname in get_missing_fields(doctype, settings) if fieldname in changed]
		if cleared:
			frappe.throw(_("{0} is required").format(_(docfields[cleared[0]].label)), frappe.MandatoryError)
		# Each row saves alone, so the other required rows may still be blank on a Single filled in bit by bit.
		settings.flags.ignore_mandatory = True
		settings.save()

	return {
		fieldname: None if docfields[fieldname].fieldtype == "Password" else settings.get(fieldname)
		for fieldname in fields
	}


def get_app_settings_doctype(app: str) -> str:
	entry = next(
		(
			entry
			for entry in get_registry()["entries"]
			if entry["app"] == app and entry["place"] == "settings"
		),
		None,
	)
	if not (
		entry
		and entry["doctype"]
		and has_required_access(entry, frappe.session.user)
		and passes_condition(entry)
	):
		frappe.throw(_("{0} has no settings here").format(app), frappe.DoesNotExistError)
	return entry["doctype"]
