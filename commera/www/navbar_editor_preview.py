# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import escape_html

from commera.shop_themes.chrome_preview import (
	COMMON_BLANKED_BLOCKS,
	FOOTER_BLOCKS,
	get_preview_context,
	preview_language,
	render_chrome_preview,
)

BASE_HEADER = "templates/includes/header.html"

no_cache = True


def get_context(context):
	frappe.has_permission("Commera Settings", "write", throw=True)

	with preview_language(frappe.form_dict.get("lang")) as lang:
		render_preview(context, lang)


def render_preview(context, lang):
	settings = frappe.get_cached_doc("Commera Settings")
	header_context = get_preview_context(settings, lang)

	rendered = render_chrome_preview(header_context, COMMON_BLANKED_BLOCKS + FOOTER_BLOCKS)
	if rendered:
		context.rendered_html = rendered
		return

	# BASE_HEADER is a path constant in this repo, never caller input.
	header_html = frappe.render_template(BASE_HEADER, header_context)  # nosemgrep: frappe-ssti

	context.rendered_html = f"""<!DOCTYPE html>
<html lang="{escape_html(lang)}" dir="{"rtl" if header_context.is_rtl else "ltr"}">
<head>
<meta charset="UTF-8">
<link rel="stylesheet" href="/assets/commera/css/tailwind.css">
{settings.generate_theme_css()}
</head>
<body>
{header_html}
</body>
</html>"""
