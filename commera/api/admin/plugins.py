# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Count
from frappe.utils.data import cint

from commera import storefront_plugins
from commera.api.admin.docfields import build_field_groups, get_editable_docfields, get_missing_fields
from commera.api.admin.integrations import write_settings
from commera.plugin_events import get_plugin_apps
from commera.plugins.places import PLACES, get_record_place_prefix
from commera.plugins.registry import (
	get_app_title,
	get_registry,
	get_registry_entry,
	get_whitelisted_method,
	has_required_access,
	passes_condition,
	resolve_record_plugins,
)

RECORD_ACTION_PLACES = frozenset(
	place for place, spec in PLACES.items() if spec["doctype"] and "method" in spec["fields"]
)
COMMAND_PLACES = frozenset({"commands"})


@frappe.whitelist()
def get_plugins() -> list[dict]:
	frappe.only_for("System Manager")

	registry = get_registry()
	failed_deliveries = get_failed_delivery_counts()
	storefront_switches = storefront_plugins.get_storefront_switches()
	return [
		{
			"app": app,
			"title": get_app_title(app),
			"icon_url": registry["apps"].get(app, {}).get("icon_url"),
			"version": getattr(frappe.get_module(app), "__version__", None),
			"entries": [
				{field: entry.get(field) for field in ("place", "name", "label", "error")}
				for entry in registry["entries"]
				if entry["app"] == app
			],
			"problems": [problem["message"] for problem in registry["problems"] if problem["app"] == app],
			"failed_deliveries": failed_deliveries.get(app, 0),
			# None for an app with no storefront hook; else whether its scripts and blocks load on store pages.
			"storefront": storefront_switches.get(app),
		}
		for app in dict.fromkeys([*get_plugin_apps(), *registry["apps"]])
	]


@frappe.whitelist(methods=["POST"])
def set_storefront_enabled(app: str, enabled: bool) -> None:
	frappe.only_for("System Manager")
	storefront_plugins.set_storefront_enabled(app, enabled)


@frappe.whitelist()
def get_plugin_deliveries(app: str, status: str | None = None, start: int = 0, page_length: int = 20) -> dict:
	frappe.only_for("System Manager")

	delivery = frappe.qb.DocType("Commera Event Delivery")
	criterion = delivery.app == app
	if status:
		criterion &= delivery.status == status
	return {
		"rows": query_deliveries(criterion, cint(start), cint(page_length)),
		"total": get_deliveries_query(criterion).select(Count("*")).run()[0][0],
	}


def get_deliveries_query(criterion):
	commera_event = frappe.qb.DocType("Commera Event")
	delivery = frappe.qb.DocType("Commera Event Delivery")
	return (
		frappe.qb.from_(delivery)
		.join(commera_event)
		.on(commera_event.name == delivery.parent)
		.where(criterion)
	)


def query_deliveries(criterion, start: int = 0, page_length: int | None = None) -> list:
	commera_event = frappe.qb.DocType("Commera Event")
	delivery = frappe.qb.DocType("Commera Event Delivery")
	query = (
		get_deliveries_query(criterion)
		.select(
			delivery.name.as_("delivery"),
			commera_event.event,
			commera_event.reference_doctype,
			commera_event.reference_name,
			delivery.app,
			delivery.status,
			delivery.attempts,
			delivery.next_retry_at,
			delivery.finished_at,
			commera_event.creation,
		)
		.orderby(commera_event.creation, order=Order.desc)
		.orderby(delivery.idx)
	)
	if page_length:
		query = query.limit(page_length).offset(start)
	rows = query.run(as_dict=True)

	# An uninstalled app keeps its deliveries but has no hooks.py to read a title from.
	installed_apps = set(frappe.get_installed_apps())
	app_titles = {
		app: get_app_title(app) if app in installed_apps else app for app in {row.app for row in rows}
	}
	can_retry = "System Manager" in frappe.get_roles()
	for row in rows:
		row.app = app_titles[row.app]
		row.can_retry = can_retry
	return rows


def get_failed_delivery_counts() -> dict:
	delivery = frappe.qb.DocType("Commera Event Delivery")
	return dict(
		frappe.qb.from_(delivery)
		.select(delivery.app, Count("*"))
		.where(delivery.status == "Failed")
		.groupby(delivery.app)
		.run()
	)


@frappe.whitelist()
def get_record_plugins(doctype: str, name: str | int) -> dict:
	place_prefix = get_record_place_prefix(doctype)
	if not place_prefix:
		frappe.throw(_("Plugins can't extend {0} records").format(doctype))

	frappe.has_permission(doctype, "read", doc=name, throw=True)
	return {"keys": resolve_record_plugins(place_prefix, name, frappe.session.user)}


@frappe.whitelist(methods=["POST"])
def run_record_action(key: str, name: str | int) -> dict:
	method = get_runnable_method(key, RECORD_ACTION_PLACES, name)
	return get_action_result(method(name=name))


@frappe.whitelist(methods=["POST"])
def run_command(key: str) -> dict:
	method = get_runnable_method(key, COMMAND_PLACES)
	return get_action_result(method())


def get_runnable_method(key: str, places: frozenset, name: str | int | None = None):
	entry = get_registry_entry(key)
	if not entry or not entry["method"] or entry["place"] not in places:
		frappe.throw(_("Plugin action {0} not found").format(key), frappe.DoesNotExistError)
	if entry.get("error"):
		frappe.throw(entry["error"])

	doctype = PLACES[entry["place"]]["doctype"]
	if doctype:
		frappe.has_permission(doctype, "read", doc=name, throw=True)
	method = get_whitelisted_method(entry["app"], entry["method"])
	condition_arguments = (doctype, name) if doctype else ()
	if not (
		method
		and has_required_access(entry, frappe.session.user)
		and passes_condition(entry, *condition_arguments)
	):
		message = (
			_("{0} isn't available for {1}").format(entry["label"], name)
			if doctype
			else _("{0} isn't available").format(entry["label"])
		)
		frappe.throw(message, frappe.PermissionError)
	return method


def get_action_result(message) -> dict:
	return {"message": message if isinstance(message, str) else None}


@frappe.whitelist()
def get_plugin_settings(app: str) -> dict:
	doctype = get_plugin_settings_doctype(app)
	frappe.has_permission(doctype, "read", throw=True)

	groups = build_field_groups(doctype, frappe.get_cached_doc(doctype))
	return {
		"doctype": doctype,
		"groups": groups,
		"values": {field["fieldname"]: field["value"] for group in groups for field in group["fields"]},
	}


@frappe.whitelist(methods=["POST"])
def save_plugin_setting(app: str, **fields):
	doctype = get_plugin_settings_doctype(app)
	frappe.has_permission(doctype, "write", throw=True)

	settings = write_settings({"settings_doctype": doctype}, fields)
	docfields = {docfield.fieldname: docfield for _group_label, docfield in get_editable_docfields(doctype)}
	changed = [
		fieldname
		for fieldname, value in fields.items()
		if not (docfields[fieldname].fieldtype == "Password" and value == "")
	]
	if changed:
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


def get_plugin_settings_doctype(app: str) -> str:
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
