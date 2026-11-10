# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import os
import re

import frappe

from commera.localization import StorefrontLanguages, resolve
from commera.shop_themes.doctype.shop_theme.shop_theme import (
	get_theme_context,
	render_theme_context,
	resolve_active_theme,
)
from commera.shop_themes.render import render_themed_template
from commera.shop_themes.theme_resolver import build_base_context, find_theme_file, run_page_controller

PREVIEW_LAYOUTS = ("components/theme_layout.html", "components/base.html")

# Blanked because they would emit tracking and canonical tags from inside an editor pane.
TRACKING_BLANKED_BLOCKS = ("seo", "json_ld", "analytics_head", "analytics_events")

# A chrome preview frames the header or the footer, so the page content between them goes too.
COMMON_BLANKED_BLOCKS = (*TRACKING_BLANKED_BLOCKS, "body", "uncontained_body")

RENDER_LAYOUT_CALL = re.compile(r"render_layout\(([^)]*)\)")

# Both naming conventions: the base theme uses `header`/`footer`, Summer `site_header`/`site_footer`.
# Not chrome_top/chrome_bottom: Summer opens .page-wraper in one and closes it in the other.
HEADER_BLOCKS = ("header", "site_header")
FOOTER_BLOCKS = ("footer", "site_footer")


def get_preview_layout(theme_context):
	"""The active theme's layout, most specific first, or None when no theme is active."""
	return next(
		(
			candidate
			for candidate in PREVIEW_LAYOUTS
			if theme_context["dirs"] and find_theme_file(theme_context["dirs"], candidate)
		),
		None,
	)


def get_preview_template(layout, blanked_blocks):
	blanks = "".join(f"{{% block {name} %}}{{% endblock %}}" for name in blanked_blocks)
	# super() keeps the theme's own head - its stylesheets - and appends the previewed colours.
	head = "{% block head %}{{ super() }}{{ preview_theme_css }}{% endblock %}"
	return f'{{% extends "{layout}" %}}{blanks}{head}'


def render_chrome_preview(context, blanked_blocks):
	"""Render the active theme's layout with `blanked_blocks` emptied, or None if no theme is active."""
	theme_name = resolve_active_theme()
	theme_context = get_theme_context(theme_name)
	layout = get_preview_layout(theme_context)
	if not layout:
		return None

	return render_themed_template(
		get_preview_template(layout, blanked_blocks), context, theme_name=theme_name
	)


def render_page_preview(page_template, blanked_blocks, theme_name=None, head_html=""):
	"""Render one of a theme's own pages whole, or None if there is no theme or it ships no such page.
	Unlike render_chrome_preview() this keeps the page content. `theme_name` previews a non-live theme."""
	theme_name = theme_name or resolve_active_theme()
	theme_context = get_theme_context(theme_name)
	if not theme_context["dirs"] or not find_theme_file(theme_context["dirs"], page_template):
		return None

	with render_theme_context(theme_context):
		# The same two steps ThemePageRenderer.render() takes for a real request, so the page gets
		# the website settings and the controller data it is written against.
		context = build_base_context(None)
		run_page_controller(theme_context["dirs"], page_template, context)

		# Nothing here is unsaved, so the head slot has no colours to append - but jinja is configured
		# with DebugUndefined, which would print the placeholder into the page rather than drop it.
		context.preview_theme_css = head_html

		return render_themed_template(
			get_preview_template(f"theme://{page_template}", blanked_blocks),
			context,
			theme_name=theme_name,
		)


def find_layout_template(theme_dirs, page):
	quoted_page = re.compile(rf"[\"']{re.escape(page)}[\"']")
	for theme_dir in theme_dirs:
		for directory, subdirectories, file_names in os.walk(os.path.join(theme_dir, "pages")):
			subdirectories.sort()
			for file_name in sorted(file_names):
				template_path = os.path.join(directory, file_name)
				relative_path = os.path.relpath(template_path, theme_dir)
				if (
					file_name.endswith(".html")
					and find_theme_file(theme_dirs, relative_path) == template_path
					and renders_layout(template_path, quoted_page)
				):
					return relative_path
	return None


def renders_layout(template_path, quoted_page):
	# nosemgrep: frappe-semgrep-rules.rules.security.frappe-security-file-traversal
	with open(template_path) as template_file:
		source = template_file.read()
	return any(quoted_page.search(arguments) for arguments in RENDER_LAYOUT_CALL.findall(source))


def get_preview_language(requested) -> str:
	"""The ?lang an editor asked for when it is a configured storefront language, else the default."""
	languages = StorefrontLanguages.load()
	return (languages.find(requested, include_unpublished=True) or languages.default).code


def get_preview_context(preview_settings, lang):
	"""The context every chrome preview needs, whichever end of the page it is rendering."""
	# Theme templates read the page language off frappe.lang, so the ?lang switch must move it here.
	frappe.local.lang = lang
	localization = resolve("/", lang, include_unpublished=True)[0]

	return frappe._dict(
		preview_settings=preview_settings,
		lang=lang,
		localization=localization,
		is_rtl=localization.language.direction == "rtl",
		# format_theme_css() in the layout reads the SAVED doc, so this live copy is appended after to win.
		preview_theme_css=preview_settings.generate_theme_css(),
		# The default theme's base renders a breadcrumb outside any block, guarded only by this.
		show_breadcrumb=False,
		commera_header_content="",
	)
