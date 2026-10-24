import re
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import create_batch

from commera.shop_themes.theme_files import (
	GROUP_TEMPLATE_PREFIX,
	get_default_layout,
	get_link_doctype,
	get_section_schemas,
	get_settings_schema,
	is_valid_setting_value,
)

MAX_SECTIONS = 25
DEFAULT_MAX_BLOCKS = 50
LAYOUT_CACHE_KEY = "commera_theme_layout"
TEMPLATE_PATTERN = re.compile(
	r"^((index|product|collection|page)(\.[a-z0-9_]+)?|group:(header|footer)|settings)$"
)
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
APP_BLOCK_PREFIX = "app:"
LAYOUT_OVERRIDES_LOCAL_KEY = "commera_theme_layout_overrides"
LINK_CHECK_BATCH_SIZE = 500
LAYOUT_INVALID = "layout-invalid"
LAYOUT_UNKNOWN_SECTION = "layout-unknown-section"
LAYOUT_UNKNOWN_BLOCK = "layout-unknown-block"


def get_layout_cache_field(theme, template):
	return f"{theme}|{template}"


def get_published_layout(theme, template):
	layout = frappe.cache.hget(
		LAYOUT_CACHE_KEY,
		get_layout_cache_field(theme, template),
		generator=lambda: fetch_published_layout(theme, template),
	)
	return layout or None


def fetch_published_layout(theme, template):
	published_layout = frappe.db.get_value(
		"Theme Layout", {"theme": theme, "template": template}, "published_layout"
	)
	return frappe.parse_json(published_layout) if published_layout else {}


def get_layout_overrides():
	overrides = getattr(frappe.local, LAYOUT_OVERRIDES_LOCAL_KEY, None)
	return overrides or {}


def get_layout(theme_context, template):
	override = get_layout_overrides().get(template)
	if override is not None:
		return override

	if theme_context["theme_name"]:
		published_layout = get_published_layout(theme_context["theme_name"], template)
		if published_layout:
			return published_layout

	return get_default_layout(theme_context["dirs"], template)


@contextmanager
def layout_override(template, layout):
	previous = getattr(frappe.local, LAYOUT_OVERRIDES_LOCAL_KEY, None)
	setattr(frappe.local, LAYOUT_OVERRIDES_LOCAL_KEY, {**(previous or {}), template: layout})
	try:
		yield
	finally:
		setattr(frappe.local, LAYOUT_OVERRIDES_LOCAL_KEY, previous)


def save_theme_layout(
	theme, template, layout, publish=False, ignore_permissions=False, synced_from_settings=False
):
	name = frappe.db.get_value("Theme Layout", {"theme": theme, "template": template})
	if name:
		theme_layout = frappe.get_doc("Theme Layout", name)
	else:
		theme_layout = frappe.new_doc("Theme Layout")
		theme_layout.update({"theme": theme, "template": template})

	theme_layout.layout = frappe.as_json(layout)
	theme_layout.flags.ignore_permissions = ignore_permissions
	theme_layout.flags.synced_from_settings = synced_from_settings
	if publish:
		theme_layout.publish()
	else:
		theme_layout.save()
	return theme_layout


def clear_layout_cache(theme, template):
	frappe.cache.hdel(LAYOUT_CACHE_KEY, get_layout_cache_field(theme, template))


def validate_layout(theme_dirs, template, layout):
	return [message for _rule, message in get_layout_findings(theme_dirs, template, layout)]


def get_layout_findings(theme_dirs, template, layout, check_links=True):
	if not isinstance(template, str) or not TEMPLATE_PATTERN.match(template):
		return [(LAYOUT_INVALID, _("{0} is not a layout template").format(template))]
	return LayoutValidator(theme_dirs, template, check_links).validate(layout)


class LayoutValidator:
	def __init__(self, theme_dirs, template, check_links=True):
		self.theme_dirs = theme_dirs
		self.template = template
		self.check_links = check_links
		self.group = (
			template[len(GROUP_TEMPLATE_PREFIX) :] if template.startswith(GROUP_TEMPLATE_PREFIX) else None
		)
		self.base_template = template.split(".")[0]
		self.schemas = get_section_schemas(theme_dirs)
		self.findings = []
		self.seen_ids = set()
		self.link_values = []

	def validate(self, layout):
		if self.template == "settings":
			self.validate_theme_settings(layout)
		else:
			self.validate_sections(layout)
		if self.check_links:
			self.validate_link_values()
		return self.findings

	def add_error(self, message, rule=LAYOUT_INVALID):
		self.findings.append((rule, message))

	def validate_theme_settings(self, layout):
		if not isinstance(layout, dict) or not isinstance(layout.get("settings"), dict):
			self.add_error(_("Theme settings need a settings object"))
			return
		self.validate_settings(get_settings_schema(self.theme_dirs), layout["settings"], _("Theme settings"))

	def validate_sections(self, layout):
		if not isinstance(layout, dict) or not isinstance(layout.get("sections"), list):
			self.add_error(_("A layout needs a sections list"))
			return

		sections = layout["sections"]
		if len(sections) > MAX_SECTIONS:
			self.add_error(_("A layout can have at most {0} sections").format(MAX_SECTIONS))

		for position, section in enumerate(sections, start=1):
			self.validate_section(section, position)
		self.validate_static_sections(sections)

	def validate_section(self, section, position):
		if not isinstance(section, dict):
			self.add_error(_("Section {0} is not an object").format(position))
			return

		section_id = section.get("id")
		self.validate_id(section_id)
		self.validate_disabled(section, section_id)

		section_type = section.get("type")
		schema = self.schemas.get(section_type) if isinstance(section_type, str) else None
		if schema is None:
			self.add_error(
				_("Section {0} has an unknown type {1}").format(section_id, section_type),
				LAYOUT_UNKNOWN_SECTION,
			)
			return

		self.validate_placement(schema, section_id, section_type)
		self.validate_settings(schema.get("settings") or [], section.get("settings"), section_id)
		self.validate_blocks(schema, section)

	def validate_id(self, element_id):
		if not isinstance(element_id, str) or not ID_PATTERN.match(element_id):
			self.add_error(_("{0} is not a valid id").format(element_id))
		elif element_id in self.seen_ids:
			self.add_error(_("The id {0} is used more than once").format(element_id))
		else:
			self.seen_ids.add(element_id)

	def validate_disabled(self, element, element_id):
		if not isinstance(element.get("disabled", False), bool):
			self.add_error(_("{0}: disabled must be true or false").format(element_id))

	def validate_placement(self, schema, section_id, section_type):
		groups = schema.get("groups")
		if self.group:
			if not groups or self.group not in groups:
				self.add_error(
					_("Section {0} ({1}) cannot be placed in the {2} group").format(
						section_id, section_type, self.group
					)
				)
			return

		if groups:
			self.add_error(
				_("Section {0} ({1}) belongs in the {2} group").format(section_id, section_type, groups[0])
			)

		templates = schema.get("templates")
		if templates and self.base_template not in templates:
			self.add_error(
				_("Section {0} ({1}) cannot be placed on {2} pages").format(
					section_id, section_type, self.base_template
				)
			)

	def validate_blocks(self, schema, section):
		section_id = section.get("id")
		blocks = section.get("blocks", [])
		if not isinstance(blocks, list):
			self.add_error(_("Section {0}: blocks must be a list").format(section_id))
			return

		max_blocks = schema.get("max_blocks") or DEFAULT_MAX_BLOCKS
		if len(blocks) > max_blocks:
			self.add_error(_("Section {0} can have at most {1} blocks").format(section_id, max_blocks))

		block_schemas = schema.get("blocks") or {}
		for position, block in enumerate(blocks, start=1):
			if not isinstance(block, dict):
				self.add_error(_("Section {0}: block {1} is not an object").format(section_id, position))
				continue
			self.validate_block(schema, block_schemas, block, section_id)

	def validate_block(self, schema, block_schemas, block, section_id):
		block_id = block.get("id")
		self.validate_id(block_id)
		self.validate_disabled(block, block_id)

		block_type = block.get("type")
		if isinstance(block_type, str) and block_type.startswith(APP_BLOCK_PREFIX):
			if not schema.get("accepts_apps"):
				self.add_error(
					_("Section {0} does not accept app blocks ({1})").format(section_id, block_type)
				)
			return

		block_schema = block_schemas.get(block_type) if isinstance(block_type, str) else None
		if block_schema is None:
			self.add_error(
				_("Block {0} in section {1} has an unknown type {2}").format(
					block_id, section_id, block_type
				),
				LAYOUT_UNKNOWN_BLOCK,
			)
			return

		self.validate_settings(block_schema.get("settings") or [], block.get("settings"), block_id)

	def validate_settings(self, setting_schemas, values, owner):
		if values is None:
			return
		if not isinstance(values, dict):
			self.add_error(_("{0}: settings must be an object").format(owner))
			return

		settings_by_id = {
			setting.get("id"): setting for setting in setting_schemas if isinstance(setting, dict)
		}
		for setting_id, value in values.items():
			setting = settings_by_id.get(setting_id)
			if setting is None:
				self.add_error(_("{0}: unknown setting {1}").format(owner, setting_id))
			elif not is_valid_setting_value(setting, value):
				self.add_error(_("{0}: {1} has an invalid value").format(owner, setting_id))
			elif value and get_link_doctype(setting):
				self.link_values.append((get_link_doctype(setting), value, owner, setting_id))

	def validate_static_sections(self, sections):
		present_types = {section.get("type") for section in sections if isinstance(section, dict)}
		for default_section in get_default_layout(self.theme_dirs, self.template).get("sections") or []:
			section_type = default_section.get("type") if isinstance(default_section, dict) else None
			schema = self.schemas.get(section_type) if isinstance(section_type, str) else None
			if schema and schema.get("static") and section_type not in present_types:
				self.add_error(_("The {0} section cannot be removed").format(section_type))

	def validate_link_values(self):
		values_by_doctype = {}
		for doctype, value, _owner, _setting_id in self.link_values:
			values_by_doctype.setdefault(doctype, set()).add(value)

		existing_by_doctype = {
			doctype: get_existing_names(doctype, values) for doctype, values in values_by_doctype.items()
		}
		for doctype, value, owner, setting_id in self.link_values:
			if value not in existing_by_doctype[doctype]:
				self.add_error(
					_("{0}: {1} links to {2} {3}, which does not exist").format(
						owner, setting_id, _(doctype), value
					)
				)


def get_existing_names(doctype, names):
	existing = set()
	for batch in create_batch(sorted(names), LINK_CHECK_BATCH_SIZE):
		existing.update(
			str(name) for name in frappe.get_all(doctype, filters={"name": ["in", batch]}, pluck="name")
		)
	return existing
