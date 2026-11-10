# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""The Commera theme bar in the Frappe Builder editor."""

import frappe

from commera.api.admin.theme import activate_theme
from commera.builder_themes import editor


@frappe.whitelist()
def get_theme_bar(page_id: str):
	frappe.has_permission("Builder Page", ptype="read", doc=page_id, throw=True)
	return editor.get_theme_bar(page_id)


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
