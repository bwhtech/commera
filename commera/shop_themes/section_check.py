import os
import re

from commera.shop_themes.theme_files import (
	RESERVED_BLOCK_TYPES,
	SETTING_TYPES,
	SNAKE_CASE_PATTERN,
	TEXT_SETTING_TYPES,
	is_number,
	is_valid_setting_value,
)

SECTION_KEYS = frozenset(
	{
		"$schema",
		"name",
		"icon",
		"settings",
		"blocks",
		"accepts_apps",
		"max_blocks",
		"presets",
		"static",
		"groups",
		"templates",
	}
)
BLOCK_KEYS = frozenset({"name", "icon", "settings", "static"})
PRESET_KEYS = frozenset({"name", "settings", "blocks"})
SETTINGS_FILE_KEYS = frozenset({"$schema", "name", "settings"})
SETTING_KEYS = frozenset({"id", "type", "label", "default", "info"})
SETTING_TYPE_KEYS = {
	**{setting_type: frozenset({"translatable"}) for setting_type in TEXT_SETTING_TYPES},
	"select": frozenset({"options"}),
	"range": frozenset({"min", "max", "step", "unit"}),
	"link": frozenset({"doctype"}),
}
SECTION_GROUPS = ("header", "footer")
BASE_TEMPLATES = ("index", "product", "collection", "page")
MAX_BLOCKS_LIMIT = 50

MACRO_PATTERN = re.compile(r"\{%-?\s*macro\s+([A-Za-z_]\w*)\s*\(")
MACRO_BODY_PATTERN = re.compile(
	r"\{%-?\s*macro\s+([A-Za-z_]\w*)\s*\(\s*([A-Za-z_]\w*)?[^)]*\)\s*-?%\}(.*?)\{%-?\s*endmacro\b", re.DOTALL
)
IMPORT_PATTERN = re.compile(r"\{%-?\s*from\s+\S+\s+import\s+(.+?)\s*-?%\}", re.DOTALL)
BLOCK_LOOP_PATTERN = re.compile(r"\{%-?\s*for\s+\w+\s+in\s+section\.blocks\b")
EXPRESSION_PATTERN = re.compile(r"\{\{(.*?)\}\}")
SAFE_FILTER_PATTERN = re.compile(r"\|\s*safe\b")


class SchemaRules:
	def is_object(self, value, file, owner):
		if isinstance(value, dict):
			return True
		self.add("schema-invalid", file, f"{owner} must be an object", "Wrap it in { }")
		return False

	def check_unknown_keys(self, data, allowed_keys, file, owner, line=None):
		for key in sorted(set(data) - allowed_keys):
			self.add(
				"schema-invalid",
				file,
				f'{owner}: unknown key "{key}"',
				f"Remove {key}; allowed keys are {', '.join(sorted(allowed_keys))}",
				line,
			)

	def check_settings(self, settings, file, owner):
		if not isinstance(settings, list):
			self.add("schema-invalid", file, f"{owner}: settings must be a list", "Use a list of settings")
			return
		seen_ids = set()
		for setting in settings:
			if not self.is_object(setting, file, f"{owner}: a setting"):
				continue
			setting_id = setting.get("id")
			line = get_line(self.read_text(file), rf'"id"\s*:\s*"{re.escape(str(setting_id))}"')
			if setting_id in seen_ids:
				self.add(
					"duplicate-setting-id",
					file,
					f'{owner}: setting id "{setting_id}" is used more than once',
					"Give each setting its own id",
					line,
				)
			seen_ids.add(setting_id)
			self.check_setting(setting, file, f'{owner} setting "{setting_id}"', line)

	def check_setting(self, setting, file, owner, line):
		setting_type = setting.get("type")
		problems = []
		if not isinstance(setting.get("id"), str) or not SNAKE_CASE_PATTERN.match(setting["id"]):
			problems.append("id must be snake_case")
		if setting_type not in SETTING_TYPES:
			problems.append(f"type must be one of {', '.join(sorted(SETTING_TYPES))}")
		problems.extend(get_setting_type_problems(setting))
		for problem in problems:
			self.add(
				"schema-invalid", file, f"{owner}: {problem}", "See commera/themes/section.schema.json", line
			)

		allowed_keys = SETTING_KEYS | SETTING_TYPE_KEYS.get(setting_type, frozenset())
		self.check_unknown_keys(setting, allowed_keys, file, owner, line)

		if "default" not in setting or problems or is_valid_setting_value(setting, setting["default"]):
			return
		if setting_type == "select":
			options = ", ".join(str(value) for value in get_option_values(setting))
			self.add(
				"select-default-invalid",
				file,
				f'{owner}: default "{setting["default"]}" is not one of {options}',
				"Set default to one of the option values",
				line,
			)
		else:
			self.add(
				"schema-invalid",
				file,
				f"{owner}: default is not a valid {setting_type} value",
				"Fix the default or remove it",
				line,
			)


class SectionSchemaChecker:
	def __init__(self, theme_checker, section_type, file):
		self.theme_checker = theme_checker
		self.section_type = section_type
		self.file = file
		self.owner = f'section "{section_type}"'

	def add_invalid(self, problem, fix="See commera/themes/section.schema.json", line=None):
		self.theme_checker.add("schema-invalid", self.file, f"{self.owner}: {problem}", fix, line)

	def check(self, schema):
		if not self.theme_checker.is_object(schema, self.file, self.owner):
			return
		if not SNAKE_CASE_PATTERN.match(self.section_type):
			self.add_invalid("the type (file name) must be snake_case", "Rename the section's files")
		self.theme_checker.check_unknown_keys(schema, SECTION_KEYS, self.file, self.owner)
		for problem in get_section_problems(schema):
			self.add_invalid(problem)
		self.theme_checker.check_settings(schema.get("settings", []), self.file, self.owner)
		self.check_blocks(schema.get("blocks", {}))
		self.check_presets(schema)

	def check_blocks(self, blocks):
		if not isinstance(blocks, dict):
			self.add_invalid("blocks must be an object keyed by block type")
			return
		text = self.theme_checker.read_text(self.file)
		for block_type, block in blocks.items():
			line = get_line(text, rf'"{re.escape(block_type)}"\s*:\s*\{{')
			block_owner = f'{self.owner} block "{block_type}"'
			if not SNAKE_CASE_PATTERN.match(block_type):
				self.add_invalid(f'block type "{block_type}" must be snake_case', line=line)
			if block_type in RESERVED_BLOCK_TYPES:
				self.theme_checker.add(
					"reserved-block-type",
					self.file,
					f'{block_owner}: "{block_type}" is reserved; a macro by that name hides the page\'s {block_type}',
					f"Rename the block type, e.g. {self.section_type}_{block_type}",
					line,
				)
			if not self.theme_checker.is_object(block, self.file, block_owner):
				continue
			self.theme_checker.check_unknown_keys(block, BLOCK_KEYS, self.file, block_owner, line)
			if not isinstance(block.get("name"), str) or not block["name"]:
				self.add_invalid(f'block "{block_type}" needs a name', line=line)
			if not isinstance(block.get("static", False), bool):
				self.add_invalid(f'block "{block_type}": static must be true or false', line=line)
			self.theme_checker.check_settings(block.get("settings", []), self.file, block_owner)

	def check_presets(self, schema):
		presets = schema.get("presets", [])
		block_types = set(schema.get("blocks") or {}) if isinstance(schema.get("blocks"), dict) else set()
		if not isinstance(presets, list):
			self.add_invalid("presets must be a list")
			return
		for position, preset in enumerate(presets, start=1):
			if not self.theme_checker.is_object(preset, self.file, f"{self.owner} preset {position}"):
				continue
			self.theme_checker.check_unknown_keys(
				preset, PRESET_KEYS, self.file, f"{self.owner} preset {position}"
			)
			for block in preset.get("blocks") or []:
				block_type = block.get("type") if isinstance(block, dict) else block
				if block_type not in block_types:
					self.add_invalid(f'preset {position} uses unknown block type "{block_type}"')


class SectionTemplateChecker:
	def __init__(self, theme_checker, schema, html_path, report_path):
		self.theme_checker = theme_checker
		self.schema = schema
		self.html_path = html_path
		self.report_path = report_path
		blocks = schema.get("blocks")
		self.blocks = blocks if isinstance(blocks, dict) else {}

	def check(self, template):
		macros = {
			match.group(1): get_line_at(template, match.start()) for match in MACRO_PATTERN.finditer(template)
		}
		imported = {
			name for match in IMPORT_PATTERN.finditer(template) for name in get_imported_names(match.group(1))
		}
		html_name = os.path.basename(self.html_path)
		for block_type in self.blocks:
			if block_type not in macros and block_type not in imported:
				self.theme_checker.add(
					"block-macro-missing",
					self.report_path,
					f'block type "{block_type}" has no {{% macro {block_type}(block) %}} in {html_name}',
					f"Add {{% macro {block_type}(block) %}} above the loop that renders the blocks",
				)
		for macro_name, line in macros.items():
			if macro_name not in self.blocks:
				self.theme_checker.add(
					"macro-without-block",
					self.html_path,
					f'macro "{macro_name}" is not a block type of this section',
					"Add the block type to the section's .json, or move the helper to components/macros/",
					line,
				)
		self.check_editor_attributes(template)
		self.check_block_loop(template)
		self.check_safe_translations(template)

	def check_editor_attributes(self, template):
		for match in MACRO_BODY_PATTERN.finditer(template):
			macro_name, parameter, body = match.groups()
			if macro_name not in self.blocks or not parameter:
				continue
			if not re.search(rf"\b{re.escape(parameter)}\.editor_attributes\b", body):
				self.theme_checker.add(
					"block-editor-attributes-missing",
					self.html_path,
					f'block macro "{macro_name}" never prints {parameter}.editor_attributes; the editor cannot select it',
					f'Print it inside the root tag: <div class="…"{{{{ {parameter}.editor_attributes }}}}>',
					get_line_at(template, match.start()),
				)

	def check_block_loop(self, template):
		has_movable_blocks = any(
			not (isinstance(block, dict) and block.get("static")) for block in self.blocks.values()
		)
		if has_movable_blocks and not BLOCK_LOOP_PATTERN.search(template):
			self.theme_checker.add(
				"blocks-not-looped",
				self.html_path,
				"section has blocks but never loops over section.blocks; reordering won't show",
				"Render blocks with {% for block in section.blocks %}{{ render_block(block) }}{% endfor %}",
			)

	def check_safe_translations(self, template):
		setting_ids = get_translatable_ids(self.schema.get("settings"))
		for block in self.blocks.values():
			if isinstance(block, dict):
				setting_ids |= get_translatable_ids(block.get("settings"))
		for line_number, line in enumerate(template.splitlines(), start=1):
			for expression in EXPRESSION_PATTERN.findall(line):
				if not SAFE_FILTER_PATTERN.search(expression):
					continue
				for setting_id in sorted(setting_ids):
					if re.search(rf"\bsettings\.{re.escape(setting_id)}\b", expression):
						self.theme_checker.add(
							"translatable-printed-safe",
							self.html_path,
							f'translatable setting "{setting_id}" is printed with |safe',
							"Drop |safe; settings are escaped for you, and merchant text must stay escaped",
							line_number,
						)


def get_section_problems(schema):
	problems = []
	if not isinstance(schema.get("name"), str) or not schema["name"]:
		problems.append("name is required")
	if not isinstance(schema.get("icon", ""), str):
		problems.append("icon must be a string")
	for key in ("accepts_apps", "static"):
		if not isinstance(schema.get(key, False), bool):
			problems.append(f"{key} must be true or false")
	max_blocks = schema.get("max_blocks", MAX_BLOCKS_LIMIT)
	if not is_number(max_blocks) or int(max_blocks) != max_blocks or not 1 <= max_blocks <= MAX_BLOCKS_LIMIT:
		problems.append(f"max_blocks must be a whole number from 1 to {MAX_BLOCKS_LIMIT}")
	groups = schema.get("groups")
	if groups is not None and not (
		isinstance(groups, list) and len(groups) == 1 and groups[0] in SECTION_GROUPS
	):
		problems.append('groups must be null, ["header"] or ["footer"]')
	templates = schema.get("templates")
	if templates is not None and not (
		isinstance(templates, list)
		and templates
		and all(template in BASE_TEMPLATES for template in templates)
	):
		problems.append(f"templates must be null or a list of {', '.join(BASE_TEMPLATES)}")
	return problems


def get_setting_type_problems(setting):
	setting_type = setting.get("type")
	problems = []
	for key in ("label", "info"):
		if not isinstance(setting.get(key, ""), str):
			problems.append(f"{key} must be a string")
	if not isinstance(setting.get("translatable", False), bool):
		problems.append("translatable must be true or false")
	if setting_type == "select" and not is_valid_options(setting.get("options")):
		problems.append('options must be a list of strings or {"value", "label"} objects')
	if setting_type == "range":
		minimum, maximum, step = setting.get("min"), setting.get("max"), setting.get("step", 1)
		if not (is_number(minimum) and is_number(maximum) and minimum <= maximum):
			problems.append("range needs numbers min and max, with min not above max")
		if not is_number(step) or step <= 0:
			problems.append("step must be a positive number")
		if not isinstance(setting.get("unit", ""), str):
			problems.append("unit must be a string")
	if setting_type == "link" and not (isinstance(setting.get("doctype"), str) and setting["doctype"]):
		problems.append("a link setting needs a doctype")
	return problems


def is_valid_options(options):
	if not isinstance(options, list) or not options:
		return False
	return all(
		isinstance(option, str)
		or (
			isinstance(option, dict)
			and isinstance(option.get("value"), str)
			and set(option) <= {"value", "label"}
		)
		for option in options
	)


def get_option_values(setting):
	return [option.get("value") if isinstance(option, dict) else option for option in setting.get("options")]


def get_translatable_ids(settings):
	if not isinstance(settings, list):
		return set()
	return {
		setting["id"]
		for setting in settings
		if isinstance(setting, dict) and setting.get("translatable") and isinstance(setting.get("id"), str)
	}


def get_imported_names(names):
	imported = set()
	for name in names.replace("with context", "").replace("without context", "").split(","):
		parts = name.split()
		if parts:
			imported.add(parts[-1])
	return imported


def get_line(text, pattern):
	match = re.search(pattern, text)
	return get_line_at(text, match.start()) if match else None


def get_line_at(text, position):
	return text.count("\n", 0, position) + 1
