import copy
import glob
import importlib.util
import json
import os
import re
from pathlib import Path

import frappe
from frappe import get_app_path

from commera.shop_themes.doctype.shop_theme.shop_theme import is_within_directory

DYNAMIC_PAGE_LANG_PREFIXES = frozenset({"en", "ar"})

SETTING_TYPES = frozenset(
	{
		"text",
		"textarea",
		"url",
		"check",
		"select",
		"range",
		"color",
		"image",
		"collection",
		"product",
		"page",
		"link",
	}
)
TEXT_SETTING_TYPES = frozenset({"text", "textarea", "url"})
LINK_DOCTYPES = {"collection": "Item Group", "product": "Style Attribute Variant", "page": "Shop Web Page"}
LINK_SETTING_TYPES = frozenset({*LINK_DOCTYPES, "link"})
COLOR_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
URL_SCHEME_PATTERN = re.compile(r"^([^/?#:]*):")
SAFE_URL_SCHEMES = frozenset({"http", "https", "mailto", "tel"})
SAFE_IMAGE_PREFIXES = ("/files/", "/private/files/", "/assets/", "http://", "https://")
IMAGE_URL_UNSAFE_PATTERN = re.compile(r"[\'\"()\\<>\x00-\x1f]")
SNAKE_CASE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
RESERVED_BLOCK_TYPES = frozenset(
	{
		"product",
		"collection",
		"page",
		"cart",
		"section",
		"block",
		"settings",
		"theme_settings",
		"request",
		"store",
		"menus",
		"search",
		"template",
	}
)

GROUP_TEMPLATE_PREFIX = "group:"

theme_file_cache = {}
theme_modules = {}


def find_theme_file(theme_dirs, relative_path):
	for theme_dir in theme_dirs:
		candidate = os.path.join(theme_dir, relative_path)
		if is_within_directory(theme_dir, candidate) and os.path.isfile(candidate):
			return candidate
	return None


def get_cached(key, generator):
	if frappe.conf.developer_mode:
		return generator()
	if key not in theme_file_cache:
		theme_file_cache[key] = generator()
	return theme_file_cache[key]


def read_json_file(path):
	return get_cached(("json", path), lambda: load_json_file(path))


def load_json_file(path):
	# nosemgrep: frappe-semgrep-rules.rules.security.frappe-security-file-traversal
	with open(path, encoding="utf-8") as json_file:
		try:
			data = json.load(json_file)
		except ValueError:
			if frappe.db:
				frappe.log_error(
					title="Theme file is not valid JSON", message=f"{path}\n\n{frappe.get_traceback()}"
				)
			return None
	return data if isinstance(data, dict) else None


def read_theme_json(theme_dirs, relative_path):
	path = find_theme_file(theme_dirs, relative_path)
	return read_json_file(path) if path else None


def list_theme_files(theme_dirs, folder, extension):
	names = set()
	for theme_dir in theme_dirs:
		folder_path = os.path.join(theme_dir, folder)
		if not os.path.isdir(folder_path):
			continue
		for filename in os.listdir(folder_path):
			stem, file_extension = os.path.splitext(filename)
			if file_extension == extension and os.path.isfile(os.path.join(folder_path, filename)):
				names.add(stem)
	return sorted(names)


def get_section_schemas(theme_dirs):
	return get_cached(("sections", tuple(theme_dirs)), lambda: load_section_schemas(theme_dirs))


def load_section_schemas(theme_dirs):
	schemas = {}
	for section_type in list_theme_files(theme_dirs, "sections", ".json"):
		schema = read_theme_json(theme_dirs, f"sections/{section_type}.json")
		if schema is not None:
			schemas[section_type] = schema
	return schemas


def get_section_schema(theme_dirs, section_type):
	return get_section_schemas(theme_dirs).get(section_type)


def get_settings_schema(theme_dirs):
	return get_cached(("settings", tuple(theme_dirs)), lambda: load_settings_schema(theme_dirs))


def load_settings_schema(theme_dirs):
	settings = (read_theme_json(theme_dirs, "settings.json") or {}).get("settings") or []
	return [setting for setting in settings if isinstance(setting, dict) and setting.get("id")]


def get_layout_file(template):
	if template.startswith(GROUP_TEMPLATE_PREFIX):
		return f"layouts/groups/{template[len(GROUP_TEMPLATE_PREFIX) :]}.json"
	return f"layouts/{template}.json"


def get_default_layout(theme_dirs, template):
	if template == "settings":
		return {"settings": {}}
	layout = read_theme_json(theme_dirs, get_layout_file(template))
	if not layout:
		return {"sections": []}
	return copy.deepcopy(layout)


def list_layout_templates(theme_dirs):
	templates = list_theme_files(theme_dirs, "layouts", ".json")
	groups = list_theme_files(theme_dirs, "layouts/groups", ".json")
	return templates + [f"{GROUP_TEMPLATE_PREFIX}{group}" for group in groups]


def load_theme_module(theme_dirs, relative_path, module_namespace):
	module_path = find_theme_file(theme_dirs, relative_path)
	if not module_path:
		return None

	modified_time = os.path.getmtime(module_path)
	cached = theme_modules.get(module_path)
	if cached and cached[0] == modified_time:
		return cached[1]

	module_name = get_theme_module_name(theme_dirs, module_path, relative_path, module_namespace)
	spec = importlib.util.spec_from_file_location(module_name, module_path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	theme_modules[module_path] = (modified_time, module)
	return module


def get_theme_module_name(theme_dirs, module_path, relative_path, module_namespace):
	theme_slug = ""
	for theme_dir in theme_dirs:
		if os.path.join(theme_dir, relative_path) == module_path:
			theme_slug = os.path.basename(theme_dir.rstrip(os.sep))
			break

	module_slug = os.path.splitext(relative_path)[0]
	for separator in (os.sep, "/", "-", "."):
		module_slug = module_slug.replace(separator, "_")

	return f"commera.shop_themes.{module_namespace}.{theme_slug}.{module_slug}"


def get_select_values(setting):
	options = setting.get("options")
	if not isinstance(options, list):
		return []
	return [option.get("value") if isinstance(option, dict) else option for option in options]


def is_translation(value):
	return (
		isinstance(value, dict)
		and set(value) <= DYNAMIC_PAGE_LANG_PREFIXES
		and all(isinstance(text, str) for text in value.values())
	)


def is_number(value):
	return isinstance(value, int | float) and not isinstance(value, bool)


def is_valid_setting_value(setting, value):
	setting_type = setting.get("type")
	if setting_type in TEXT_SETTING_TYPES:
		texts = [value] if isinstance(value, str) else None
		if texts is None and setting.get("translatable") and is_translation(value):
			texts = list(value.values())
		return texts is not None and (setting_type != "url" or all(is_safe_url(text) for text in texts))
	if setting_type == "check":
		return isinstance(value, bool)
	if setting_type == "select":
		return isinstance(value, str | int | float) and value in get_select_values(setting)
	if setting_type == "range":
		return is_number(value) and is_within_range(setting, value)
	if setting_type == "color":
		return isinstance(value, str) and (value == "" or bool(COLOR_PATTERN.match(value)))
	if setting_type == "image":
		return isinstance(value, str) and is_safe_image_url(value)
	if setting_type in LINK_SETTING_TYPES:
		return isinstance(value, str)
	return False


def is_safe_url(value):
	scheme = URL_SCHEME_PATTERN.match(value.strip())
	return not scheme or scheme.group(1).lower() in SAFE_URL_SCHEMES


def is_safe_image_url(value):
	return value == "" or (
		value.startswith(SAFE_IMAGE_PREFIXES) and not IMAGE_URL_UNSAFE_PATTERN.search(value)
	)


def is_within_range(setting, value):
	minimum = setting.get("min")
	maximum = setting.get("max")
	return (not is_number(minimum) or value >= minimum) and (not is_number(maximum) or value <= maximum)


def get_setting_default(setting):
	default = setting.get("default")
	if default is not None and is_valid_setting_value(setting, default):
		return copy.deepcopy(default)

	setting_type = setting.get("type")
	if setting_type == "check":
		return False
	if setting_type == "select":
		values = get_select_values(setting)
		return values[0] if values else ""
	if setting_type == "range":
		minimum = setting.get("min")
		return minimum if is_number(minimum) else 0
	return ""


def get_link_doctype(setting):
	if setting.get("type") == "link":
		return setting.get("doctype")
	return LINK_DOCTYPES.get(setting.get("type"))


def get_theme_records_on_disk(apps_path=None):
	records = {}
	for app, package_path in get_app_package_paths(apps_path):
		for record_path in sorted(glob.glob(os.path.join(package_path, "*", "shop_theme", "*", "*.json"))):
			record = load_record_file(record_path)
			if record and record.get("doctype") == "Shop Theme" and record.get("name"):
				slug = frappe.scrub(record["name"])
				records[slug] = {
					"name": record["name"],
					"parent_theme": record.get("parent_theme"),
					"app": app,
					"record_path": record_path,
					"theme_dir": os.path.join(package_path, "themes", slug),
				}
	return records


def get_app_package_paths(apps_path=None):
	if apps_path is None:
		return [(app, get_app_path(app)) for app in frappe.get_all_apps(with_internal_apps=False)]
	return [
		(app, os.path.join(apps_path, app, app))
		for app in sorted(os.listdir(apps_path))
		if os.path.isfile(os.path.join(apps_path, app, app, "modules.txt"))
	]


def load_record_file(path):
	try:
		record = json.loads(Path(path).read_text())
	except (OSError, ValueError):
		return None
	return record if isinstance(record, dict) else None


def find_theme_dirs_on_disk(slug, apps_path=None):
	return get_theme_chain_dirs(get_theme_records_on_disk(apps_path), slug)


def get_theme_chain_dirs(records, slug):
	dirs = []
	visited = set()
	while slug in records and slug not in visited:
		visited.add(slug)
		record = records[slug]
		if os.path.isdir(record["theme_dir"]):
			dirs.append(record["theme_dir"])
		slug = frappe.scrub(record["parent_theme"]) if record["parent_theme"] else None
	return dirs
