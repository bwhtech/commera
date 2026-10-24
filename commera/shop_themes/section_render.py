import re

import frappe
from jinja2 import pass_context
from jinja2.runtime import Macro
from markupsafe import Markup, escape

from commera.shop_themes.doctype.shop_theme.shop_theme import get_render_theme_context
from commera.shop_themes.layouts import APP_BLOCK_PREFIX, get_layout
from commera.shop_themes.section_data import block_products_cache
from commera.shop_themes.theme_files import (
	get_section_schemas,
	get_setting_default,
	get_settings_schema,
	is_valid_setting_value,
	load_theme_module,
)

EDITOR_LOCAL_KEY = "commera_theme_editor"
ERROR_THROTTLE_SECONDS = 600
ERROR_THROTTLE_CACHE_PREFIX = "commera_theme_section_error"
ESCAPED_SETTING_TYPES = frozenset(
	{"text", "textarea", "url", "image", "collection", "product", "page", "link"}
)
CSS_SETTING_TYPES = frozenset({"color", "range", "select"})
CSS_VARIABLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@pass_context
def render_layout(context, template):
	theme_context = get_render_theme_context()
	schemas = get_section_schemas(theme_context["dirs"])
	language = get_language()
	theme_settings = get_context_theme_settings(context, theme_context)

	html = []
	with block_products_cache():
		for layout_template in ("group:header", template, "group:footer"):
			layout = get_layout(theme_context, layout_template)
			sections = resolve_sections(layout, schemas, language)
			page = frappe._dict(context.get_all())
			page.layout_sections = sections
			for section in sections:
				html.append(
					render_section(context, theme_context, layout_template, section, page, theme_settings)
				)
	return Markup("".join(html))


def resolve_sections(layout, schemas, language):
	sections = []
	for stored_section in (layout or {}).get("sections") or []:
		if not isinstance(stored_section, dict) or stored_section.get("disabled"):
			continue
		section_type = stored_section.get("type")
		schema = schemas.get(section_type) if isinstance(section_type, str) else None
		if schema is not None:
			sections.append(resolve_section(schema, stored_section, language))
	return sections


def render_section(context, theme_context, template, section, page, theme_settings):
	try:
		controller_data = run_section_controller(theme_context["dirs"], section, page)
		section_template = context.environment.get_template(f"theme://sections/{section.type}.html")
		html = section_template.render(
			{**context.get_all(), "theme_settings": theme_settings, **controller_data, "section": section}
		)
	except Exception as error:
		log_section_error(
			theme_context["theme_name"],
			f"{template}|{section.id}",
			f"Theme section {section.type} failed",
		)
		if is_editor_mode() or frappe.conf.developer_mode:
			message = frappe._("Section {0} could not be rendered").format(section.type)
			if frappe.conf.developer_mode:
				message = f"{message}: {error}"
			return format_section_placeholder(section, message, "error")
		return ""

	if not html.strip():
		if is_editor_mode():
			return format_section_placeholder(
				section, frappe._("Section {0} has nothing to show yet").format(section.type), "empty"
			)
		return ""
	return format_section_wrapper(section, html)


def run_section_controller(theme_dirs, section, page):
	module = load_theme_module(theme_dirs, f"sections/{section.type}.py", "theme_sections")
	if not module or not hasattr(module, "get_context"):
		return {}
	return module.get_context(section, page) or {}


def format_section_wrapper(section, html, state_attribute=""):
	editor_attribute = Markup(' data-section-id="{0}"').format(section.id) if is_editor_mode() else ""
	return (
		Markup('<section id="section-{0}" data-section-type="{1}"{2}{3}>').format(
			section.id, section.type, editor_attribute, state_attribute
		)
		+ Markup(html)
		+ Markup("</section>")
	)


def format_section_placeholder(section, message, state):
	return format_section_wrapper(
		section, Markup("<p>{0}</p>").format(message), Markup(' data-section-{0}="1"').format(state)
	)


@pass_context
def render_block(context, block):
	block_type = block.get("type") if isinstance(block, dict) else None
	if not isinstance(block_type, str) or block_type.startswith(APP_BLOCK_PREFIX):
		return Markup("")

	macro = context.vars.get(block_type)
	if not isinstance(macro, Macro):
		section = context.get("section") or {}
		log_section_error(
			get_render_theme_context()["theme_name"],
			f"{section.get('id')}|{block_type}",
			f"Theme block {block_type} has no macro",
			message=f"sections/{section.get('type')}.html defines no macro named {block_type}",
		)
		return Markup("")

	return Markup(macro(block))


@pass_context
def render_static_block(context, block_type):
	section = context.get("section") or frappe._dict()
	static_blocks = section.get("static_blocks") or {}
	if block_type not in static_blocks:
		log_section_error(
			get_render_theme_context()["theme_name"],
			f"{section.get('id')}|{block_type}",
			f"Theme block {block_type} is not a static block",
			message=f"sections/{section.get('type')}.json declares no static block {block_type}",
		)
		return Markup("")

	block = static_blocks[block_type]
	if block is None:
		return Markup("")
	return render_block(context, block)


def resolve_section(schema, stored_section, language):
	block_schemas = schema.get("blocks") or {}
	blocks = []
	static_blocks = frappe._dict()

	for stored_block in stored_section.get("blocks") or []:
		if not isinstance(stored_block, dict):
			continue
		block_type = stored_block.get("type")
		block_schema = block_schemas.get(block_type) if isinstance(block_type, str) else None
		if block_schema is None:
			continue

		if block_schema.get("static"):
			if block_type not in static_blocks:
				disabled = stored_block.get("disabled")
				static_blocks[block_type] = (
					None if disabled else resolve_block(block_schema, stored_block, language)
				)
		elif not stored_block.get("disabled"):
			block = resolve_block(block_schema, stored_block, language)
			block.index = len(blocks) + 1
			blocks.append(block)

	for block_type, block_schema in block_schemas.items():
		if block_schema.get("static") and block_type not in static_blocks:
			static_blocks[block_type] = resolve_block(
				block_schema, {"id": block_type, "type": block_type}, language
			)

	return frappe._dict(
		id=stored_section.get("id"),
		type=stored_section.get("type"),
		settings=resolve_settings(schema.get("settings") or [], stored_section.get("settings"), language),
		blocks=blocks,
		static_blocks=static_blocks,
	)


def resolve_block(block_schema, stored_block, language):
	return frappe._dict(
		id=stored_block.get("id"),
		type=stored_block.get("type"),
		settings=resolve_settings(block_schema.get("settings") or [], stored_block.get("settings"), language),
		editor_attributes=get_block_editor_attributes(stored_block.get("id")),
	)


def get_block_editor_attributes(block_id):
	if not is_editor_mode():
		return Markup("")
	return Markup(' data-block-id="{0}"').format(block_id)


def resolve_settings(setting_schemas, stored_values, language):
	stored_values = stored_values if isinstance(stored_values, dict) else {}
	settings = frappe._dict()
	for setting in setting_schemas:
		if isinstance(setting, dict) and setting.get("id"):
			settings[setting["id"]] = resolve_setting_value(
				setting, stored_values.get(setting["id"]), language
			)
	return settings


def resolve_setting_value(setting, value, language):
	if not is_valid_setting_value(setting, value):
		value = get_setting_default(setting)

	if isinstance(value, dict):
		value = value.get(language) or value.get("en") or ""

	if setting.get("type") in ESCAPED_SETTING_TYPES:
		return escape(value)
	return value


def get_theme_settings(theme_context):
	setting_schemas = get_settings_schema(theme_context["dirs"])
	if not setting_schemas:
		return frappe._dict()
	layout = get_layout(theme_context, "settings")
	return resolve_settings(setting_schemas, (layout or {}).get("settings"), get_language())


def get_context_theme_settings(context, theme_context):
	theme_settings = context.get("theme_settings")
	return get_theme_settings(theme_context) if theme_settings is None else theme_settings


@pass_context
def format_theme_settings_css(context):
	theme_context = get_render_theme_context()
	setting_schemas = get_settings_schema(theme_context["dirs"])
	if not setting_schemas:
		return Markup("")

	settings = get_context_theme_settings(context, theme_context)
	declarations = []
	for setting in setting_schemas:
		setting_id = setting.get("id")
		value = settings.get(setting_id)
		if (
			setting.get("type") not in CSS_SETTING_TYPES
			or not isinstance(setting_id, str)
			or not CSS_VARIABLE_ID_PATTERN.match(setting_id)
			or value in ("", None)
		):
			continue
		unit = setting.get("unit") if setting.get("type") == "range" else None
		declarations.append(f"--theme-{setting_id}: {value}{unit or ''};")

	if not declarations:
		return Markup("")
	return Markup("<style>:root{{{0}}}</style>").format(Markup(" ".join(declarations)))


def get_language():
	return getattr(frappe.local, "lang", None) or "en"


def is_editor_mode():
	return bool(getattr(frappe.local, EDITOR_LOCAL_KEY, None))


def log_section_error(theme_name, throttle_key, title, message=None):
	cache_key = f"{ERROR_THROTTLE_CACHE_PREFIX}|{theme_name}|{throttle_key}"
	if frappe.cache.get_value(cache_key, expires=True):
		return
	frappe.cache.set_value(cache_key, 1, expires_in_sec=ERROR_THROTTLE_SECONDS)
	frappe.log_error(title=title, message=message, reference_doctype="Shop Theme", reference_name=theme_name)
