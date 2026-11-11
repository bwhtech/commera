# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import escape_html
from markupsafe import Markup

from commera.localization.languages import is_rtl_language
from commera.shop_themes.chrome_preview import (
	TRACKING_BLANKED_BLOCKS,
	find_layout_template,
	preview_language,
	render_page_preview,
)
from commera.shop_themes.doctype.shop_theme.shop_theme import get_theme_context, resolve_active_theme
from commera.shop_themes.preview_entries import PREVIEW_ENTRY_PAGES, resolve_entry
from commera.shop_themes.sections import SECTION_GROUPS
from commera.shop_themes.theme_resolver import find_theme_file

no_cache = True

HOME_PAGE_TEMPLATE = "pages/index.html"
EDITOR_ROLES = ("System Manager", "Website Manager")

EDITOR_HEAD_HTML = Markup(
	"<style>[data-commera-section]{display:contents}</style>"
	'<script defer src="/assets/commera/js/theme_editor_preview.js"></script>'
)


def get_context(context):
	frappe.only_for(EDITOR_ROLES)

	theme = requested_theme()
	theme_dirs = get_theme_context(theme or resolve_active_theme())["dirs"]
	page = requested_page(theme_dirs)
	layouts = requested_layouts(page)

	with preview_language(frappe.form_dict.get("lang")) as lang:
		render_preview(context, theme, theme_dirs, page, layouts, lang)


def render_preview(context, theme, theme_dirs, page, layouts, lang):
	page_template = find_page_template(theme_dirs, page)
	sample_form = get_sample_form(page) if page_template else None
	rendered = sample_form is not None and render_layout_page(page_template, sample_form, theme, layouts)
	if rendered:
		context.rendered_html = rendered
		return

	message = no_preview_message(theme, page, page_template)
	editor_hint = f'<p class="mt-2 text-base">{escape_html(_("You can still edit this layout."))}</p>'
	context.rendered_html = f"""<!DOCTYPE html>
<html lang="{escape_html(lang)}" dir="{"rtl" if is_rtl_language(lang) else "ltr"}">
<head>
<meta charset="UTF-8">
<link rel="stylesheet" href="/assets/commera/css/tailwind.css">
{EDITOR_HEAD_HTML if layouts else ""}
</head>
<body class="grid min-h-screen place-items-center bg-gray-50 p-6 text-center text-gray-500">
<div class="max-w-sm">
<p class="text-xl font-medium text-gray-900">{escape_html(message)}</p>
{editor_hint if layouts else ""}
</div>
</body>
</html>"""


def find_page_template(theme_dirs, page):
	page_template = find_layout_template(theme_dirs, page)
	if not page_template and page == "index" and find_theme_file(theme_dirs, HOME_PAGE_TEMPLATE):
		return HOME_PAGE_TEMPLATE
	return page_template


def render_layout_page(page_template, sample_form, theme, layouts):
	request_form = frappe.local.form_dict
	frappe.local.form_dict = sample_form
	if layouts:
		frappe.local.theme_editor_preview = frappe._dict(layouts=layouts)
	try:
		return render_page_preview(
			page_template,
			TRACKING_BLANKED_BLOCKS,
			theme_name=theme,
			head_html=EDITOR_HEAD_HTML if layouts else "",
		)
	finally:
		frappe.local.theme_editor_preview = None
		frappe.local.form_dict = request_form


def requested_theme():
	"""The installed theme the pane asked for, or None to fall back to the live one."""
	theme = frappe.form_dict.get("theme")
	if not theme or not frappe.db.exists("Shop Theme", theme):
		return None

	return theme


def requested_page(theme_dirs):
	page = frappe.form_dict.get("page") or "index"
	if page == "index":
		return page
	if (
		not isinstance(page, str)
		or not page.replace("_", "").replace("-", "").isalnum()
		or not find_theme_file(theme_dirs, f"layouts/{page}.json")
	):
		frappe.throw(_("This theme has no {0} page to preview.").format(page), frappe.DoesNotExistError)

	return page


def requested_layouts(page):
	parts = {page: "layout", **{group: f"{group}_layout" for group in SECTION_GROUPS}}
	return {
		part: requested_layout(field)
		for part, field in parts.items()
		if frappe.form_dict.get(field) is not None
	}


def requested_layout(field):
	layout = frappe.parse_json(frappe.form_dict.get(field))
	if not isinstance(layout, dict) or not isinstance(layout.get("sections"), list):
		frappe.throw(_('A layout must be an object with a "sections" list.'))

	return layout


def no_preview_message(theme, page, page_template):
	if page_template and page == "page":
		return frappe._("Publish a page to preview the page layout.")
	if page_template:
		return frappe._("Publish a product to preview the {0} page.").format(page)
	if page != "index":
		return frappe._("This theme has no {0} page to preview.").format(page)
	if theme:
		return frappe._("{0} has no home page to preview.").format(theme)

	return frappe._("The live theme has no home page to preview.")


def get_sample_form(page):
	if page not in PREVIEW_ENTRY_PAGES:
		return frappe._dict()

	entry = resolve_entry(page, frappe.form_dict.get("entry"))
	if entry is None:
		return None
	if page == "search":
		return frappe._dict(search=entry["value"])
	if page == "products":
		return frappe._dict(category=entry["value"]) if entry["value"] else frappe._dict()
	return frappe._dict(route=entry["value"])
