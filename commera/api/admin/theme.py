# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""The Theme screen: which theme is live, and the settings that theme ships of its own."""

import frappe
from frappe.utils import get_url_to_form

from commera.api.admin.docfields import build_field_groups, get_child_tables, get_editable_docfields
from commera.api.admin.settings import coerce_field_value
from commera.shop_themes.doctype.shop_theme.shop_theme import get_theme_context, resolve_active_theme

THEME_SETTINGS_DOCTYPE = "Shop Theme Settings"


def get_theme_settings_doctype(theme):
	return get_theme_context(theme)["settings_doctype"]


def build_themes(active_theme):
	"""Every installed theme, live one first, with what each inherits from."""
	themes = frappe.get_all(
		"Shop Theme",
		fields=["name", "theme_name", "parent_theme", "is_standard", "theme_settings", "theme_type"],
		order_by="theme_name asc",
	)

	for theme in themes:
		theme.live = theme.name == active_theme

	return sorted(themes, key=lambda theme: not theme.live)


def build_theme_settings(active_theme):
	"""The live theme's own settings, rendered from its docfield meta."""
	settings_doctype = get_theme_settings_doctype(active_theme)
	if not settings_doctype:
		return {"doctype": None, "groups": [], "child_tables": [], "desk_url": None}

	frappe.has_permission(settings_doctype, ptype="read", throw=True)

	settings = frappe.get_cached_doc(settings_doctype)
	return {
		"doctype": settings_doctype,
		"groups": build_field_groups(settings_doctype, settings),
		# Slides, banners and pinned products are rows, not fields: the screen links out to them
		# rather than pretending they are editable here.
		"child_tables": get_child_tables(settings_doctype, settings),
		"desk_url": get_url_to_form(settings_doctype, settings_doctype),
	}


def build_editor_data():
	frappe.has_permission(THEME_SETTINGS_DOCTYPE, ptype="read", throw=True)

	active_theme = resolve_active_theme()
	return {
		"active_theme": active_theme,
		"themes": build_themes(active_theme),
		"settings": build_theme_settings(active_theme),
	}


@frappe.whitelist()
def get_editor_data():
	"""Everything the Theme screen renders, in one read."""
	return build_editor_data()


@frappe.whitelist(methods=["POST"])
def activate_theme(theme: str):
	"""Make one installed theme the live storefront. Returns the refreshed screen."""
	frappe.has_permission(THEME_SETTINGS_DOCTYPE, ptype="write", throw=True)

	if not frappe.db.exists("Shop Theme", theme):
		frappe.throw(frappe._("Theme {0} is not installed on this site").format(theme))

	# Saved as a Document, never db_set: on_update is what clears the compiled routes and the
	# memoised render context, and a themed page keeps serving the old theme without it.
	settings = frappe.get_doc(THEME_SETTINGS_DOCTYPE)
	settings.active_theme = theme
	settings.save()

	return build_editor_data()


@frappe.whitelist(methods=["POST"])
def save_theme_settings(**values):
	"""Write the live theme's own settings. Returns the refreshed screen."""
	frappe.has_permission(THEME_SETTINGS_DOCTYPE, ptype="read", throw=True)

	settings_doctype = get_theme_settings_doctype(resolve_active_theme())
	if not settings_doctype:
		frappe.throw(frappe._("The live theme has no settings to save"))

	frappe.has_permission(settings_doctype, ptype="write", throw=True)

	write_docfield_values(settings_doctype, values)
	return build_editor_data()


def write_docfield_values(settings_doctype, values):
	"""Save only the fields this screen actually renders, each cast by its own docfield type."""
	docfield_by_fieldname = {
		docfield.fieldname: docfield for _group_label, docfield in get_editable_docfields(settings_doctype)
	}

	unknown_fieldnames = set(values) - set(docfield_by_fieldname)
	if unknown_fieldnames:
		frappe.throw(
			frappe._("{0} has no field {1}").format(settings_doctype, ", ".join(sorted(unknown_fieldnames)))
		)

	settings = frappe.get_doc(settings_doctype)
	for fieldname, value in values.items():
		settings.set(fieldname, coerce_field_value(docfield_by_fieldname[fieldname].fieldtype, value))

	settings.save()
	return settings
