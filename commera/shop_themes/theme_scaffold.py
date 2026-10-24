import os
from datetime import datetime
from pathlib import Path

import click
import frappe

from commera.shop_themes.doctype.shop_theme.shop_theme import THEME_NAME_PATTERN
from commera.shop_themes.theme_files import (
	SNAKE_CASE_PATTERN,
	get_app_package_paths,
	get_default_layout,
	get_theme_chain_dirs,
	get_theme_records_on_disk,
	read_theme_json,
)

EMPTY_LAYOUT = {"sections": []}
EMPTY_SETTINGS = {"name": "Theme settings", "settings": []}
SCAFFOLD_LAYOUTS = ("index", "page")


def create_theme(apps_path, app, slug, parent="shop_base_theme", theme_name=None, module=None):
	package_path = dict(get_app_package_paths(apps_path)).get(app)
	if not package_path:
		raise click.UsageError(f"{app} is not an app on this bench; create it with bench new-app")
	modules = get_app_modules(package_path, app)
	records = get_theme_records_on_disk(apps_path)
	validate_new_slug(apps_path, records, slug)

	parent_dirs = get_theme_chain_dirs(records, parent)
	if not parent_dirs:
		raise click.UsageError(
			f"No parent theme {parent} on disk; pass --parent with an existing theme's slug"
		)

	theme_name = theme_name or slug.replace("_", " ").title()
	if not THEME_NAME_PATTERN.match(theme_name) or frappe.scrub(theme_name) != slug:
		raise click.UsageError(
			f'--name "{theme_name}" must use letters, numbers and spaces and scrub to {slug}'
		)

	module = module or modules[0]
	if module not in modules:
		raise click.UsageError(f"{module} is not a module of {app}; pick one of {', '.join(modules)}")

	parent_settings = read_theme_json(parent_dirs, "settings.json") or EMPTY_SETTINGS
	theme_dir = os.path.join(package_path, "themes", slug)
	record_dir = os.path.join(package_path, frappe.scrub(module), "shop_theme", slug)
	files = {
		os.path.join(theme_dir, "settings.json"): parent_settings,
		os.path.join(theme_dir, "sections", ".gitkeep"): "",
		**{
			os.path.join(theme_dir, "layouts", f"{template}.json"): get_default_layout(parent_dirs, template)
			for template in SCAFFOLD_LAYOUTS
		},
		os.path.join(theme_dir, "layouts", "groups", "header.json"): EMPTY_LAYOUT,
		os.path.join(theme_dir, "layouts", "groups", "footer.json"): EMPTY_LAYOUT,
		os.path.join(os.path.dirname(record_dir), "__init__.py"): "",
		os.path.join(record_dir, "__init__.py"): "",
		os.path.join(record_dir, f"{slug}.json"): get_theme_record(
			theme_name, module, records[parent]["name"]
		),
	}
	created = [write_new_file(path, content) for path, content in files.items()]
	app_root = os.path.dirname(package_path)
	return {"theme": theme_name, "created": [os.path.relpath(path, app_root) for path in created if path]}


def get_app_modules(package_path, app):
	modules_text = Path(package_path, "modules.txt").read_text()
	modules = [line.strip() for line in modules_text.splitlines() if line.strip()]
	if not modules:
		raise click.UsageError(f"{app}/modules.txt lists no module; add one or pass --module")
	return modules


def validate_new_slug(apps_path, records, slug):
	if not SNAKE_CASE_PATTERN.match(slug):
		raise click.UsageError(f"--slug {slug} must be snake_case, e.g. atelier or summer_sale")
	if slug in records:
		raise click.UsageError(
			f"The theme {slug} already exists in {records[slug]['app']}; pick another slug"
		)
	for app, package_path in get_app_package_paths(apps_path):
		if os.path.exists(os.path.join(package_path, "themes", slug)):
			raise click.UsageError(f"{app}/themes/{slug} already exists; pick another slug")


def get_theme_record(theme_name, module, parent_theme_name):
	timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
	return {
		"creation": timestamp,
		"docstatus": 0,
		"doctype": "Shop Theme",
		"idx": 0,
		"is_standard": 1,
		"modified": timestamp,
		"modified_by": "Administrator",
		"module": module,
		"name": theme_name,
		"owner": "Administrator",
		"parent_theme": parent_theme_name,
		"theme_name": theme_name,
	}


def write_new_file(path, content):
	if os.path.exists(path):
		return None
	os.makedirs(os.path.dirname(path), exist_ok=True)
	Path(path).write_text(content if isinstance(content, str) else frappe.as_json(content) + "\n")
	return path
