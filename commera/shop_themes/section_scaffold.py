import json
import os
import re
from pathlib import Path

import click
import frappe

from commera.shop_themes.section_check import BASE_TEMPLATES
from commera.shop_themes.theme_files import (
	RESERVED_BLOCK_TYPES,
	SNAKE_CASE_PATTERN,
	get_default_layout,
	get_layout_file,
	get_section_schemas,
	get_theme_chain_dirs,
	get_theme_records_on_disk,
)
from commera.shop_themes.theme_scaffold import write_new_file

BLOCK_SETTINGS = [{"id": "text", "type": "textarea", "label": "Text", "translatable": True}]
SECTION_SETTINGS = [{"id": "heading", "type": "text", "label": "Heading", "translatable": True}]
CONTROLLER = "def get_context(section, page):\n\treturn {}\n"
END_MACRO_PATTERN = re.compile(r"\{%-?\s*endmacro\s*-?%\}\n?")


def create_section(
	theme, section_type, blocks=(), group=None, templates=(), static=False, controller=False, apps_path=None
):
	theme_dirs = get_own_theme_dirs(theme, apps_path)
	validate_type(section_type, "--type")
	if section_type in get_section_schemas(theme_dirs):
		raise click.UsageError(f"The section {section_type} already exists in {theme} or a parent theme")
	for block_type in blocks:
		validate_block_type(block_type, ())
	unknown_templates = set(templates) - set(BASE_TEMPLATES)
	if unknown_templates:
		raise click.UsageError(
			f"--templates takes {', '.join(BASE_TEMPLATES)}, not {', '.join(sorted(unknown_templates))}"
		)

	sections_dir = os.path.join(theme_dirs[0], "sections")
	schema = {
		"$schema": get_schema_path(sections_dir),
		"name": get_label(section_type),
		"settings": SECTION_SETTINGS,
		**({"blocks": {block_type: get_block_schema(block_type) for block_type in blocks}} if blocks else {}),
		**({"presets": [{"blocks": list(blocks)}]} if blocks else {}),
		**({"static": True} if static else {}),
		**({"groups": [group]} if group else {}),
		**({"templates": list(templates)} if templates else {}),
	}
	files = {
		os.path.join(sections_dir, f"{section_type}.html"): format_section_template(blocks),
		os.path.join(sections_dir, f"{section_type}.json"): format_schema(schema),
	}
	if controller:
		files[os.path.join(sections_dir, f"{section_type}.py")] = CONTROLLER
	created = [write_new_file(path, content) for path, content in files.items()]
	if static:
		created.extend(add_static_section(theme_dirs, section_type, templates))
	return {"theme": theme, "created": [os.path.relpath(path, theme_dirs[0]) for path in created if path]}


def create_block(theme, section_type, block_type, static=False, apps_path=None):
	theme_dirs = get_own_theme_dirs(theme, apps_path)
	json_path = os.path.join(theme_dirs[0], "sections", f"{section_type}.json")
	html_path = os.path.join(theme_dirs[0], "sections", f"{section_type}.html")
	if not (os.path.isfile(json_path) and os.path.isfile(html_path)):
		raise click.UsageError(f"{theme} has no sections/{section_type}.json and .html of its own")

	try:
		schema = json.loads(Path(json_path).read_text())
	except ValueError:
		raise click.UsageError(
			f"sections/{section_type}.json is not valid JSON; run bench commera theme check"
		)
	blocks = schema.setdefault("blocks", {})
	validate_block_type(block_type, blocks)
	blocks[block_type] = {**get_block_schema(block_type), **({"static": True} if static else {})}

	Path(json_path).write_text(format_schema(schema))
	Path(html_path).write_text(add_block_macro(Path(html_path).read_text(), block_type))
	return {"theme": theme, "changed": [f"sections/{section_type}.json", f"sections/{section_type}.html"]}


def get_own_theme_dirs(theme, apps_path):
	records = get_theme_records_on_disk(apps_path)
	theme_dirs = get_theme_chain_dirs(records, theme)
	if not theme_dirs or theme_dirs[0] != records[theme]["theme_dir"]:
		raise click.UsageError(f"No theme folder with a Shop Theme record for {theme}; check --theme")
	return theme_dirs


def validate_type(type_name, option):
	if not SNAKE_CASE_PATTERN.match(type_name):
		raise click.UsageError(f"{option} {type_name} must be snake_case, e.g. testimonials")


def validate_block_type(block_type, existing_blocks):
	validate_type(block_type, "block type")
	if block_type in RESERVED_BLOCK_TYPES:
		raise click.UsageError(
			f"{block_type} is reserved for page context; name the block e.g. {block_type}_card"
		)
	if block_type in existing_blocks:
		raise click.UsageError(f"The block {block_type} already exists in this section")


def get_schema_path(sections_dir):
	schema_path = frappe.get_app_path("commera", "themes", "section.schema.json")
	return os.path.relpath(os.path.realpath(schema_path), os.path.realpath(sections_dir))


def get_label(type_name):
	return type_name.replace("_", " ").capitalize()


def get_block_schema(block_type):
	return {"name": get_label(block_type), "settings": BLOCK_SETTINGS}


def format_schema(schema):
	return json.dumps(schema, indent="\t", ensure_ascii=False) + "\n"


def format_block_macro(block_type):
	return f"{{% macro {block_type}(block) %}}\n\t<div{{{{ block.editor_attributes }}}}>{{{{ block.settings.text }}}}</div>\n{{% endmacro %}}\n"


def format_section_template(blocks):
	macros = "\n".join(format_block_macro(block_type) for block_type in blocks)
	loop = "\t{% for block in section.blocks %}{{ render_block(block) }}{% endfor %}\n" if blocks else ""
	body = f'<div class="container">\n\t<h2>{{{{ section.settings.heading }}}}</h2>\n{loop}</div>\n'
	return f"{macros}\n{body}" if macros else body


def add_block_macro(template, block_type):
	end_tags = list(END_MACRO_PATTERN.finditer(template))
	if not end_tags:
		return f"{format_block_macro(block_type)}\n{template}"
	position = end_tags[-1].end()
	return f"{template[:position]}\n{format_block_macro(block_type)}{template[position:]}"


def add_static_section(theme_dirs, section_type, templates):
	changed = []
	for template in templates:
		layout_path = os.path.join(theme_dirs[0], get_layout_file(template))
		layout = get_default_layout(theme_dirs, template)
		layout.setdefault("sections", []).append({"id": section_type, "type": section_type})
		os.makedirs(os.path.dirname(layout_path), exist_ok=True)
		Path(layout_path).write_text(format_schema(layout))
		changed.append(layout_path)
	return changed
