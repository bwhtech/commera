# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""Rendering any settings Single as dashboard fields, straight off its own docfield meta.
Adding a docfield surfaces it on every screen that edits a Single this way - integrations, theme settings."""

import frappe
from frappe.utils.data import cstr

# Fieldtypes the generic renderer cannot express as a single input.
SKIPPED_FIELDTYPES = frozenset({"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Table"})

# A tab heads its own fields as much as a section does; without it the first fields of a tab
# inherit the last section label of the tab before them.
GROUP_BREAK_FIELDTYPES = frozenset({"Section Break", "Tab Break"})

# Neutral on purpose: "Credentials" put Razorpay's Test Mode switch under a heading promising API keys.
DEFAULT_GROUP_LABEL = "General"


def get_editable_docfields(settings_doctype, excluded_fieldnames=frozenset()):
	"""Every docfield a store owner may fill in, in Desk layout order, tagged with its group label."""
	docfields = []
	group_label = DEFAULT_GROUP_LABEL

	for docfield in frappe.get_meta(settings_doctype).fields:
		if docfield.fieldtype in GROUP_BREAK_FIELDTYPES:
			group_label = docfield.label or DEFAULT_GROUP_LABEL
			continue
		if docfield.fieldtype in SKIPPED_FIELDTYPES:
			continue
		if docfield.hidden or docfield.read_only or docfield.fieldname in excluded_fieldnames:
			continue

		docfields.append((group_label, docfield))

	return docfields


def build_field(docfield, settings):
	"""One docfield as the dashboard sees it. A secret reports whether it is stored, never what it is."""
	stored_value = settings.get(docfield.fieldname)
	is_secret = docfield.fieldtype == "Password"

	return {
		"fieldname": docfield.fieldname,
		"label": docfield.label,
		"fieldtype": docfield.fieldtype,
		"options": docfield.options,
		"description": docfield.description,
		"required": bool(docfield.reqd),
		"value": None if is_secret else stored_value,
		"is_secret": is_secret,
		"is_set": stored_value not in (None, ""),
	}


def build_field_groups(settings_doctype, settings, excluded_fieldnames=frozenset()):
	"""The settings Single rendered as groups of fields, one group per section or tab."""
	groups = []
	group_by_label = {}

	for group_label, docfield in get_editable_docfields(settings_doctype, excluded_fieldnames):
		group = group_by_label.get(group_label)
		if group is None:
			group = {"label": group_label, "fields": []}
			group_by_label[group_label] = group
			groups.append(group)

		group["fields"].append(build_field(docfield, settings))

	return groups


def get_missing_fields(settings_doctype, settings, excluded_fieldnames=frozenset()):
	"""Required fieldnames still blank on the settings Single."""
	return [
		docfield.fieldname
		for _group_label, docfield in get_editable_docfields(settings_doctype, excluded_fieldnames)
		if docfield.reqd and settings.get(docfield.fieldname) in (None, "")
	]


def get_child_tables(settings_doctype, settings):
	"""The Table fields the generic renderer skips, so a screen can at least point at them."""
	return [
		{
			"fieldname": docfield.fieldname,
			"label": docfield.label,
			"options": docfield.options,
			"count": len(settings.get(docfield.fieldname) or []),
		}
		for docfield in frappe.get_meta(settings_doctype).fields
		if docfield.fieldtype == "Table" and not docfield.hidden
	]


def get_linked_doctypes(doctype):
	"""Every doctype reachable through a Link field on `doctype` — what a picker may search."""
	return {
		docfield.options
		for docfield in frappe.get_meta(doctype).fields
		if docfield.fieldtype == "Link" and docfield.options
	}


def search_link_options(doctype, search_text=None, filters=None):
	"""Matching records as a picker's options. The CALLER owns the guard on which doctype may be
	searched — this only shapes the answer.
	"""
	frappe.has_permission(doctype, ptype="read", throw=True)

	filters = dict(filters or {})
	if search_text:
		filters["name"] = ("like", f"%{cstr(search_text)}%")

	# ponytail: first 100 matches only - the picker searches server-side, so anything further
	# down is reachable by typing; paginate if a doctype outgrows even a searched list
	records = frappe.get_all(doctype, filters=filters, pluck="name", order_by="name asc", limit=100)
	return [{"label": name, "value": name} for name in records]
