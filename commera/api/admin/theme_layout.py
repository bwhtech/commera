# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import os

import frappe
from frappe import _
from frappe.core.doctype.file.utils import decode_file_content

from commera.api.admin.theme import build_theme_settings
from commera.shop_themes.doctype.shop_theme.shop_theme import get_theme_context, resolve_active_theme
from commera.shop_themes.preview_entries import PREVIEW_ENTRY_PAGES, list_entries, resolve_entry
from commera.shop_themes.sections import get_inherited_layout, get_section_schema

EDITOR_ROLES = ("System Manager", "Website Manager")
MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024
THUMBNAIL_FIELDS = {"light": "thumbnail", "dark": "thumbnail_dark"}


def get_editable_theme_context(theme):
	frappe.only_for(EDITOR_ROLES)

	if not frappe.db.exists("Shop Theme", theme):
		frappe.throw(_("Theme {0} is not installed on this site").format(theme), frappe.DoesNotExistError)

	theme_context = get_theme_context(theme)
	if theme_context["theme_type"] != "Sections":
		frappe.throw(_("{0} is a Classic theme, so it has no layouts to edit.").format(theme))
	return theme_context


def list_theme_files(theme_dirs, folder):
	names = set()
	for theme_dir in theme_dirs:
		folder_path = os.path.join(theme_dir, folder)
		if os.path.isdir(folder_path):
			names.update(
				file_name[: -len(".json")]
				for file_name in os.listdir(folder_path)
				if file_name.endswith(".json")
			)
	return sorted(names)


def get_pages(theme_dirs):
	return list_theme_files(theme_dirs, "layouts")


def validate_page(theme_context, page):
	if page not in get_pages(theme_context["dirs"]):
		frappe.throw(_("{0} has no layout for page {1}.").format(theme_context["theme_name"], page))


def get_section_schemas(theme_dirs):
	schemas = []
	for section_type in list_theme_files(theme_dirs, "sections"):
		schema = get_section_schema(theme_dirs, section_type)
		if schema:
			schemas.append({**schema, "type": section_type})
	return sorted(schemas, key=lambda schema: (schema.get("category") or "", schema.get("name") or ""))


def get_theme_layout_name(theme, page):
	return frappe.db.get_value("Theme Layout", {"theme": theme, "page": page})


def parse_layout(layout):
	return frappe.parse_json(layout) if layout else None


def get_default_layout(theme_context, page):
	return get_inherited_layout(theme_context["names"][1:], theme_context["dirs"], page)


def build_layout_state(theme_context, page):
	default_layout = get_default_layout(theme_context, page)
	saved = (
		frappe.db.get_value(
			"Theme Layout",
			{"theme": theme_context["theme_name"], "page": page},
			["draft_layout", "published_layout"],
			as_dict=True,
		)
		or frappe._dict()
	)

	published_layout = parse_layout(saved.published_layout)
	live_layout = published_layout or default_layout
	draft_layout = parse_layout(saved.draft_layout) or live_layout
	return {
		"page": page,
		"draft_layout": draft_layout,
		"published_layout": published_layout,
		"default_layout": default_layout,
		"has_unpublished_changes": draft_layout != live_layout,
	}


@frappe.whitelist()
def get_editor(theme: str, page: str = "index"):
	theme_context = get_editable_theme_context(theme)
	validate_page(theme_context, page)

	return {
		"theme": theme,
		"theme_type": theme_context["theme_type"],
		"live": theme == resolve_active_theme(),
		"pages": get_pages(theme_context["dirs"]),
		"section_schemas": get_section_schemas(theme_context["dirs"]),
		"settings": build_theme_settings(theme),
		"has_preview_entries": page in PREVIEW_ENTRY_PAGES,
		**build_layout_state(theme_context, page),
	}


@frappe.whitelist()
def get_preview_entries(
	theme: str, page: str, search: str | None = None, start: int = 0, selected: str | None = None
):
	validate_page(get_editable_theme_context(theme), page)

	return {**list_entries(page, search, start), "current": resolve_entry(page, selected)}


def save_draft_layout(theme_context, page, layout):
	layout = frappe.parse_json(layout)
	if layout is None:
		frappe.throw(_("A layout is required."))

	name = get_theme_layout_name(theme_context["theme_name"], page)
	theme_layout = (
		frappe.get_doc("Theme Layout", name)
		if name
		else frappe.new_doc("Theme Layout", theme=theme_context["theme_name"], page=page)
	)
	theme_layout.draft_layout = frappe.as_json(layout)
	theme_layout.save()
	return theme_layout


@frappe.whitelist(methods=["POST"])
def save_draft(theme: str, page: str, layout: str | dict):
	theme_context = get_editable_theme_context(theme)
	validate_page(theme_context, page)

	save_draft_layout(theme_context, page, layout)
	return build_layout_state(theme_context, page)


@frappe.whitelist(methods=["POST"])
def publish(theme: str, page: str, layout: str | dict):
	theme_context = get_editable_theme_context(theme)
	validate_page(theme_context, page)

	save_draft_layout(theme_context, page, layout).publish()
	return build_layout_state(theme_context, page)


def detect_image_extension(content):
	if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
		return "webp"
	if content.startswith(b"\x89PNG"):
		return "png"
	if content.startswith(b"\xff\xd8\xff"):
		return "jpg"
	return None


@frappe.whitelist(methods=["POST"])
def save_thumbnail(theme: str, image: str, scheme: str = "light"):
	get_editable_theme_context(theme)
	if scheme not in THUMBNAIL_FIELDS:
		frappe.throw(_("A thumbnail is either for light or for dark mode."))
	fieldname = THUMBNAIL_FIELDS[scheme]

	content = decode_file_content(image)
	extension = detect_image_extension(content)
	if not extension:
		frappe.throw(_("A thumbnail must be a WebP, PNG or JPEG image."))
	if len(content) > MAX_THUMBNAIL_BYTES:
		frappe.throw(_("A thumbnail must be smaller than 2 MB."))

	previous_files = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Shop Theme",
			"attached_to_name": theme,
			"attached_to_field": fieldname,
		},
		pluck="name",
	)

	thumbnail = frappe.get_doc(
		doctype="File",
		file_name=f"{frappe.scrub(theme)}-{fieldname}-{frappe.generate_hash(length=8)}.{extension}",
		content=content,
		is_private=0,
		attached_to_doctype="Shop Theme",
		attached_to_name=theme,
		attached_to_field=fieldname,
	).insert()

	frappe.db.set_value("Shop Theme", theme, fieldname, thumbnail.file_url, update_modified=False)

	for file_name in previous_files:
		frappe.delete_doc("File", file_name, ignore_permissions=True)

	return thumbnail.file_url


@frappe.whitelist(methods=["POST"])
def discard(theme: str, page: str):
	theme_context = get_editable_theme_context(theme)
	validate_page(theme_context, page)

	name = get_theme_layout_name(theme, page)
	if name:
		theme_layout = frappe.get_doc("Theme Layout", name)
		theme_layout.draft_layout = theme_layout.published_layout or frappe.as_json(
			get_default_layout(theme_context, page)
		)
		theme_layout.save()

	return build_layout_state(theme_context, page)
