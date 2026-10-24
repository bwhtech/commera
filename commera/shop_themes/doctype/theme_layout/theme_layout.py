# Copyright (c) 2026, BWH Tech and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, create_batch

from commera.shop_themes.doctype.shop_theme.shop_theme import get_theme_context
from commera.shop_themes.theme_files import (
	GROUP_TEMPLATE_PREFIX,
	get_default_layout,
	get_link_doctype,
	get_section_schemas,
	get_setting_default,
	is_valid_setting_value,
)

MAX_SECTIONS = 25
DEFAULT_MAX_BLOCKS = 50
LAYOUT_CACHE_KEY = "commera_theme_layout"
TEMPLATE_PATTERN = re.compile(r"^((index|product|collection|page)(\.[a-z0-9_]+)?|group:(header|footer))$")
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
APP_BLOCK_PREFIX = "app:"
LINK_CHECK_BATCH_SIZE = 500


class ThemeLayout(Document):
	def validate(self):
		if not TEMPLATE_PATTERN.match(self.template or ""):
			frappe.throw(_("{0} is not a layout template").format(self.template))
		self.validate_unique_template()
		self.is_synced_from_settings = 1 if self.flags.synced_from_settings else 0
		LayoutValidator(get_theme_context(self.theme)["dirs"], self.template).validate(self.sections)

	def validate_unique_template(self):
		filters = {"theme": self.theme, "template": self.template, "name": ("!=", self.name or "")}
		if frappe.db.exists("Theme Layout", filters):
			frappe.throw(
				_("Theme {0} already has a layout for {1}").format(self.theme, self.template),
				frappe.DuplicateEntryError,
			)

	def on_change(self):
		self.clear_cache_after_commit(self.theme, self.template)
		previous = self.get_doc_before_save()
		if previous and (previous.theme, previous.template) != (self.theme, self.template):
			self.clear_cache_after_commit(previous.theme, previous.template)

	def on_trash(self):
		self.clear_cache_after_commit(self.theme, self.template)

	def clear_cache_after_commit(self, theme, template):
		clear_layout_cache(theme, template)
		frappe.db.after_commit.add(lambda: clear_layout_cache(theme, template))
		frappe.db.after_rollback.add(lambda: clear_layout_cache(theme, template))


class LayoutValidator:
	def __init__(self, theme_dirs, template):
		self.theme_dirs = theme_dirs
		self.template = template
		self.group = (
			template.removeprefix(GROUP_TEMPLATE_PREFIX)
			if template.startswith(GROUP_TEMPLATE_PREFIX)
			else None
		)
		self.schemas = get_section_schemas(theme_dirs)
		self.seen_ids = set()
		self.link_values = []

	def validate(self, rows):
		if len(rows) > MAX_SECTIONS:
			frappe.throw(_("A layout can have at most {0} sections").format(MAX_SECTIONS))
		for row in rows:
			self.validate_row(row)
		self.validate_static_sections(rows)
		self.validate_link_values()

	def throw(self, row, message):
		frappe.throw(_("Row #{0}: {1}").format(row.idx, message), title=_("Invalid layout"))

	def validate_row(self, row):
		self.validate_id(row, row.section_id)
		schema = self.schemas.get(row.section_type)
		if schema is None:
			self.throw(row, _("Section Type {0} is not a section of this theme").format(row.section_type))

		self.validate_placement(row, schema)
		params = self.parse_json(row, "params", {})
		row.params = frappe.as_json(self.get_settings(row, schema.get("settings"), params, _("Params")))
		row.blocks = frappe.as_json(self.get_blocks(row, schema))

	def parse_json(self, row, fieldname, default):
		try:
			return frappe.parse_json(row.get(fieldname) or default)
		except ValueError:
			self.throw(row, _("{0} is not valid JSON").format(_(row.meta.get_label(fieldname))))

	def validate_id(self, row, element_id):
		if not isinstance(element_id, str) or not ID_PATTERN.match(element_id):
			self.throw(row, _("{0} is not a valid id").format(element_id))
		if element_id in self.seen_ids:
			self.throw(row, _("The id {0} is used more than once").format(element_id))
		self.seen_ids.add(element_id)

	def validate_placement(self, row, schema):
		groups = schema.get("groups") or []
		if self.group:
			if self.group not in groups:
				self.throw(
					row, _("{0} cannot be placed in the {1} group").format(row.section_type, self.group)
				)
			return
		if groups:
			self.throw(row, _("{0} belongs in the {1} group").format(row.section_type, groups[0]))

		templates = schema.get("templates")
		page_type = self.template.split(".")[0]
		if templates and page_type not in templates:
			self.throw(row, _("{0} cannot be placed on {1} pages").format(row.section_type, page_type))

	def get_blocks(self, row, schema):
		blocks = self.parse_json(row, "blocks", [])
		if not isinstance(blocks, list):
			self.throw(row, _("Blocks must be a list"))
		max_blocks = schema.get("max_blocks") or DEFAULT_MAX_BLOCKS
		if len(blocks) > max_blocks:
			self.throw(row, _("{0} can have at most {1} blocks").format(row.section_type, max_blocks))
		return [
			self.get_block(row, schema, block, position) for position, block in enumerate(blocks, start=1)
		]

	def get_block(self, row, schema, block, position):
		if not isinstance(block, dict):
			self.throw(row, _("Blocks: block {0} is not an object").format(position))
		block_id = block.get("id")
		self.validate_id(row, block_id)

		block_type = block.get("type")
		if isinstance(block_type, str) and block_type.startswith(APP_BLOCK_PREFIX):
			if not schema.get("accepts_apps"):
				self.throw(
					row, _("{0} does not accept app blocks ({1})").format(row.section_type, block_type)
				)
			return block

		block_schema = (schema.get("blocks") or {}).get(block_type) if isinstance(block_type, str) else None
		if block_schema is None:
			self.throw(row, _("Blocks: {0} has an unknown type {1}").format(block_id, block_type))

		settings = self.get_settings(row, block_schema.get("settings"), block.get("settings") or {}, block_id)
		resolved_block = {"id": block_id, "type": block_type, "settings": settings}
		if block.get("disabled"):
			resolved_block["disabled"] = True
		return resolved_block

	def get_settings(self, row, setting_schemas, values, owner):
		if not isinstance(values, dict):
			self.throw(row, _("{0}: settings must be an object").format(owner))

		settings = {}
		for setting in setting_schemas or []:
			setting_id = setting.get("id") if isinstance(setting, dict) else None
			if not setting_id:
				continue
			value = values.get(setting_id)
			if value is None:
				settings[setting_id] = get_setting_default(setting)
				continue

			value = coerce_setting_value(setting, value)
			if not is_valid_setting_value(setting, value):
				self.throw(row, _("{0}: {1} has an invalid value").format(owner, setting_id))
			if value and get_link_doctype(setting):
				self.link_values.append((get_link_doctype(setting), value, row, f"{owner}: {setting_id}"))
			settings[setting_id] = value
		return settings

	def validate_static_sections(self, rows):
		placed_types = {row.section_type for row in rows}
		for section in get_default_layout(self.theme_dirs, self.template).get("sections") or []:
			section_type = section.get("type") if isinstance(section, dict) else None
			schema = self.schemas.get(section_type) or {}
			if schema.get("static") and section_type not in placed_types:
				frappe.throw(_("The {0} section cannot be removed").format(section_type))

	def validate_link_values(self):
		names_by_doctype = {}
		for doctype, value, _row, _label in self.link_values:
			names_by_doctype.setdefault(doctype, set()).add(value)

		existing_by_doctype = {
			doctype: get_existing_names(doctype, names) for doctype, names in names_by_doctype.items()
		}
		for doctype, value, row, label in self.link_values:
			if value not in existing_by_doctype[doctype]:
				self.throw(
					row, _("{0} links to {1} {2}, which does not exist").format(label, _(doctype), value)
				)


def coerce_setting_value(setting, value):
	if setting.get("type") == "check" and value in (0, 1, "0", "1"):
		return bool(cint(value))
	if setting.get("type") == "range" and isinstance(value, str):
		try:
			number = float(value)
		except ValueError:
			return value
		return int(number) if number.is_integer() else number
	return value


def get_existing_names(doctype, names):
	existing = set()
	for batch in create_batch(sorted(names), LINK_CHECK_BATCH_SIZE):
		existing.update(
			str(name) for name in frappe.get_all(doctype, filters={"name": ["in", batch]}, pluck="name")
		)
	return existing


def get_layout(theme_context, template):
	if theme_context["theme_name"]:
		saved_layout = get_saved_layout(theme_context["theme_name"], template)
		if saved_layout:
			return saved_layout
	return get_default_layout(theme_context["dirs"], template)


def get_saved_layout(theme, template):
	layout = frappe.cache.hget(
		LAYOUT_CACHE_KEY, f"{theme}|{template}", generator=lambda: fetch_saved_layout(theme, template)
	)
	return layout or None


def fetch_saved_layout(theme, template):
	theme_layout = frappe.qb.DocType("Theme Layout")
	section = frappe.qb.DocType("Theme Layout Section")
	rows = (
		frappe.qb.from_(section)
		.join(theme_layout)
		.on(section.parent == theme_layout.name)
		.select(section.section_id, section.section_type, section.hidden, section.params, section.blocks)
		.where(theme_layout.theme == theme)
		.where(theme_layout.template == template)
		.where(section.parenttype == "Theme Layout")
		.where(section.parentfield == "sections")
		.orderby(section.idx)
		.run(as_dict=True)
	)
	if not rows:
		return {}
	return {
		"sections": [
			{
				"id": row.section_id,
				"type": row.section_type,
				"disabled": bool(row.hidden),
				"settings": frappe.parse_json(row.params) or {},
				"blocks": frappe.parse_json(row.blocks) or [],
			}
			for row in rows
		]
	}


def clear_layout_cache(theme, template):
	frappe.cache.hdel(LAYOUT_CACHE_KEY, f"{theme}|{template}")


def save_theme_layout(theme, template, layout, ignore_permissions=False, synced_from_settings=False):
	name = frappe.db.get_value("Theme Layout", {"theme": theme, "template": template})
	if name:
		theme_layout = frappe.get_doc("Theme Layout", name)
	else:
		theme_layout = frappe.new_doc("Theme Layout", theme=theme, template=template)

	theme_layout.set(
		"sections",
		[
			{
				"section_id": section.get("id"),
				"section_type": section.get("type"),
				"hidden": cint(section.get("disabled")),
				"params": frappe.as_json(section.get("settings") or {}),
				"blocks": frappe.as_json(section.get("blocks") or []),
			}
			for section in layout["sections"]
		],
	)
	theme_layout.flags.ignore_permissions = ignore_permissions
	theme_layout.flags.synced_from_settings = synced_from_settings
	theme_layout.save()
	return theme_layout


def on_doctype_update():
	frappe.db.add_unique("Theme Layout", ["theme", "template"], constraint_name="unique_theme_template")
