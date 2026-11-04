import os
import re

import frappe
from frappe.model import no_value_fields
from markupsafe import Markup

from commera.shop_themes.doctype.shop_theme.shop_theme import (
	STYLE_TAB,
	get_render_theme_context,
	is_within_directory,
)

UNSAFE_CSS_VALUE = re.compile(r"[;{}<>\\]|/\*")


def shop_theme_asset_url(path):
	"""Resolve a public asset against the theme inheritance chain, child first.
	Name is app-prefixed: jinja hook methods share one global dict by function name and the last app wins.
	"""
	theme_context = get_render_theme_context()
	if not theme_context["theme_name"]:
		return ""

	relative_path = path.lstrip("/")
	asset_url = find_theme_asset_url(theme_context, relative_path)
	if asset_url:
		return asset_url

	# Nothing in the chain ships it: fall back to the ACTIVE theme's URL so the 404 names this theme.
	active_name = theme_context["names"][0]
	active_app = theme_context["apps"][active_name]
	return f"/assets/{active_app}/themes/{frappe.scrub(active_name)}/{relative_path}"


def find_theme_asset_url(theme_context, relative_path):
	for name in theme_context["names"]:
		app = theme_context["apps"][name]
		slug = frappe.scrub(name)
		theme_public_dir = os.path.join(frappe.get_app_path(app), "public", "themes", slug)
		asset_path = os.path.join(theme_public_dir, relative_path)
		if is_within_directory(theme_public_dir, asset_path) and os.path.isfile(asset_path):
			return f"/assets/{app}/themes/{slug}/{relative_path}"
	return None


def shop_theme_config():
	"""The active theme's settings Single, for reading FIELDS off in a template.
	Never call a controller method on it from a template: jinja's SafeDoc wrapper resolves methods to None.
	"""
	theme_context = get_render_theme_context()
	settings_doctype = theme_context.get("settings_doctype")
	if not settings_doctype:
		return frappe._dict()

	return frappe.get_cached_doc(settings_doctype)


def get_shop_theme_settings():
	settings_doctype = get_render_theme_context().get("settings_doctype")
	if not settings_doctype:
		return frappe._dict()

	return frappe._dict(frappe.get_cached_doc(settings_doctype).as_dict(no_default_fields=True))


def format_shop_theme_css():
	settings_doctype = get_render_theme_context().get("settings_doctype")
	if not settings_doctype:
		return ""

	settings = get_shop_theme_settings()
	declarations = []
	for fieldname in get_style_fieldnames(settings_doctype):
		value = settings.get(fieldname)
		if value in (None, "") or UNSAFE_CSS_VALUE.search(str(value)):
			continue
		declarations.append(f"--theme-{fieldname.replace('_', '-')}: {str(value).strip()};")

	if not declarations:
		return ""
	return Markup(f'<style id="shop-theme-settings">:root{{{" ".join(declarations)}}}</style>')


def get_style_fieldnames(settings_doctype):
	fieldnames = []
	in_style_tab = False
	for docfield in frappe.get_meta(settings_doctype).fields:
		if docfield.fieldtype == "Tab Break":
			in_style_tab = docfield.fieldname == STYLE_TAB
		elif in_style_tab and docfield.fieldtype not in no_value_fields:
			fieldnames.append(docfield.fieldname)
	return fieldnames
