# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""Renders the storefront footer with the *unsaved* Desk form values for the footer editor's iframe."""

import re

import frappe
from frappe.utils import cstr, escape_html, validate_url

from commera.commera_ecommerce.doctype.commera_settings.editor_input import SAFE_URL_SCHEMES
from commera.shop_themes.chrome_preview import (
	COMMON_BLANKED_BLOCKS,
	HEADER_BLOCKS,
	get_preview_context,
	preview_language,
	render_chrome_preview,
)

BASE_FOOTER = "templates/includes/footer.html"

no_cache = True

PREVIEW_OVERRIDE_FIELDS = (
	"newsletter_title",
	"newsletter_description",
	"copyright_text",
	"contact_phone",
	"contact_email",
	"working_hours",
	"store_name",
	"footer_logo",
	"payment_methods_image",
	"vat_certificate_image",
	"facebook_url",
	"instagram_url",
	"twitter_url",
	"tiktok_url",
	"snapchat_url",
	"footer_bg_color",
	"footer_text_color",
)

# These land inside the <style> block generate_theme_css() builds, where escaping is no defence —
# only an exact hex match keeps `#fff};x:expression(1)` out of the stylesheet.
COLOR_FIELDS = ("footer_bg_color", "footer_text_color")
COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{3}([0-9a-fA-F]{3}([0-9a-fA-F]{2})?)?$")

# The footers escape these themselves; escaping here too would show `&amp;` for `&`.
ESCAPED_IN_TEMPLATE = ("store_name", "copyright_text")

# These land in an href/src attribute, so escaping is not enough either — javascript: and data:
# survive escaping intact.
URL_FIELDS = (
	"footer_logo",
	"payment_methods_image",
	"vat_certificate_image",
	"facebook_url",
	"instagram_url",
	"twitter_url",
	"tiktok_url",
	"snapchat_url",
)


def get_context(context):
	frappe.has_permission("Commera Settings", "write", throw=True)

	settings = frappe.get_single("Commera Settings")
	for fieldname in PREVIEW_OVERRIDE_FIELDS:
		value = frappe.form_dict.get(fieldname)
		# Werkzeug hands back a list when a param repeats.
		if isinstance(value, list | tuple):
			value = value[0] if value else None
		value = cstr(value) if value is not None else ""
		if not value:
			continue

		if fieldname in COLOR_FIELDS:
			if not COLOR_PATTERN.match(value):
				continue
		else:
			if fieldname in URL_FIELDS and not validate_url(value, valid_schemes=SAFE_URL_SCHEMES):
				continue
			if fieldname not in ESCAPED_IN_TEMPLATE:
				value = escape_html(value)

		setattr(settings, fieldname, value)

	with preview_language(frappe.form_dict.get("lang")) as lang:
		render_preview(context, settings, lang)


def render_preview(context, settings, lang):
	footer_context = get_preview_context(settings, lang)

	rendered = render_chrome_preview(footer_context, COMMON_BLANKED_BLOCKS + HEADER_BLOCKS)
	if rendered:
		context.rendered_html = rendered
		return

	# BASE_FOOTER is a path constant in this repo, never caller input.
	footer_html = frappe.render_template(BASE_FOOTER, footer_context)  # nosemgrep: frappe-ssti

	context.rendered_html = f"""<!DOCTYPE html>
<html lang="{escape_html(lang)}" dir="{"rtl" if footer_context.is_rtl else "ltr"}">
<head>
<meta charset="UTF-8">
<link rel="stylesheet" href="/assets/commera/css/tailwind.css">
{settings.generate_theme_css()}
</head>
<body>
{footer_html}
</body>
</html>"""
