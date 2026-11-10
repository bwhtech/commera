import os

import frappe
from markupsafe import Markup

from commera.shop_themes.theme_resolver import get_commera_header_content

BEHAVIOURS_SCRIPT = "js/commera-builder.js"


def commera_builder_head() -> Markup:
	"""Jinja method for a Builder theme page's head: the storefront SDK and the data-commera-* behaviours."""
	html = get_commera_header_content() + f'<script src="{get_behaviours_url()}" defer></script>'
	return Markup(html)  # nosemgrep: frappe-semgrep-rules.rules.security.frappe-markup


def get_behaviours_url() -> str:
	# The file is not part of a bundle, so its own modified time busts the browser cache.
	version = int(os.path.getmtime(frappe.get_app_path("commera", "public", BEHAVIOURS_SCRIPT)))
	return f"/assets/commera/{BEHAVIOURS_SCRIPT}?v={version}"
