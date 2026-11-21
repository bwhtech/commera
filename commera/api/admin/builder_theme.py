# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""The Commera theme bar in the Frappe Builder editor, and the Store themes view in its dashboard."""

import frappe

from commera.api.admin.theme import activate_theme
from commera.builder_themes import editor
from commera.builder_themes.theme import create_builder_theme


@frappe.whitelist()
def get_theme_bar(page_id: str):
	frappe.has_permission("Builder Page", ptype="read", doc=page_id, throw=True)
	return editor.get_theme_bar(page_id)


@frappe.whitelist()
def get_theme_access():
	"""Whether the Store themes view shows for this user, and whether it offers New theme."""
	return {
		"can_read": bool(frappe.has_permission("Shop Theme", ptype="read")),
		"can_create": bool(frappe.has_permission("Shop Theme", ptype="create")),
	}


@frappe.whitelist()
def get_themes():
	frappe.has_permission("Shop Theme", ptype="read", throw=True)
	return editor.get_themes()


@frappe.whitelist()
def get_theme(theme: str):
	frappe.has_permission("Shop Theme", ptype="read", doc=theme, throw=True)
	return editor.get_theme(theme)


@frappe.whitelist(methods=["POST"])
def create_theme(theme_name: str):
	"""A new Builder theme with three empty pages. Returns it as the Store themes view shows it."""
	frappe.has_permission("Shop Theme", ptype="create", throw=True)
	return editor.get_theme(create_builder_theme(theme_name.strip()).name)


@frappe.whitelist()
def search_preview_products(query: str | None = None):
	frappe.has_permission("Builder Page", ptype="read", throw=True)
	return editor.search_products(query)


@frappe.whitelist(methods=["POST"])
def publish_theme(theme: str):
	"""Publish the theme's designed pages. Returns which were published and which were left empty."""
	frappe.has_permission("Shop Theme", ptype="read", doc=theme, throw=True)
	return editor.publish_theme(theme)


@frappe.whitelist(methods=["POST"])
def make_theme_live(theme: str):
	activate_theme(theme)
	return {"is_live": True}
