import json
import os
import re
from pathlib import Path

import click
import frappe

from commera.shop_themes.doctype.shop_theme.shop_theme import build_theme_context
from commera.shop_themes.layouts import get_layout_findings
from commera.shop_themes.section_check import (
	BASE_TEMPLATES,
	SETTINGS_FILE_KEYS,
	SchemaRules,
	SectionSchemaChecker,
	SectionTemplateChecker,
)
from commera.shop_themes.theme_files import (
	GROUP_TEMPLATE_PREFIX,
	find_theme_file,
	get_default_layout,
	get_layout_file,
	get_section_schema,
	get_section_schemas,
	get_theme_chain_dirs,
	get_theme_records_on_disk,
	list_theme_files,
)

ERROR = "error"
WARNING = "warning"
RULE_SEVERITY = {
	"invalid-json": ERROR,
	"schema-invalid": ERROR,
	"duplicate-setting-id": ERROR,
	"select-default-invalid": ERROR,
	"block-macro-missing": ERROR,
	"macro-without-block": ERROR,
	"section-template-missing": ERROR,
	"reserved-block-type": ERROR,
	"layout-invalid": ERROR,
	"layout-unknown-section": ERROR,
	"layout-unknown-block": ERROR,
	"static-section-missing": ERROR,
	"blocks-not-looped": WARNING,
	"block-editor-attributes-missing": WARNING,
	"physical-css-property": WARNING,
	"translatable-printed-safe": WARNING,
	"template-without-layout": WARNING,
}
LAYOUT_FIXES = {
	"layout-invalid": "Fix the layout as the message says; bench commera theme check --json lists every problem",
	"layout-unknown-section": "Add sections/<type>.json and .html to the theme, or remove the section",
	"layout-unknown-block": "Add the block type to the section's blocks, or remove the block",
}

RENDER_LAYOUT_PATTERN = re.compile(r"render_layout\(\s*[\"']([^\"']+)[\"']")
PHYSICAL_CSS_PATTERNS = (
	(re.compile(r"(?<![\w-])(margin|padding|border)-(left|right)((?:-[a-z]+)?)\s*:"), None),
	(re.compile(r"(?<![\w-])(left|right)\s*:"), None),
	(re.compile(r"(?<![\w-])text-align\s*:\s*(left|right)\b"), "text-align"),
)
LOGICAL_SIDES = {"left": "inline-start", "right": "inline-end"}


class ThemeChecker(SchemaRules):
	def __init__(self, theme_dirs):
		self.theme_dirs = theme_dirs
		self.theme_dir = theme_dirs[0]
		self.texts = {}
		self.json_files = {}
		self.findings = []

	def check(self):
		self.check_json_files()
		self.check_settings_file()
		for section_type in self.get_own_section_types():
			self.check_section(section_type)
		self.check_layouts()
		self.check_static_sections()
		self.check_physical_css()
		self.check_pages()
		return sorted(self.findings, key=lambda finding: (finding["file"], finding["line"] or 0))

	def add(self, rule, file, message, fix, line=None):
		self.findings.append(
			{
				"rule": rule,
				"severity": RULE_SEVERITY[rule],
				"file": file,
				"line": line,
				"message": message,
				"fix": fix,
			}
		)

	def owns(self, relative_path):
		return os.path.isfile(os.path.join(self.theme_dir, relative_path))

	def read_text(self, relative_path):
		if relative_path not in self.texts:
			self.texts[relative_path] = Path(self.theme_dir, relative_path).read_text()
		return self.texts[relative_path]

	def list_own_files(self, folder, extension):
		return [
			f"{folder}/{stem}{extension}" for stem in list_theme_files([self.theme_dir], folder, extension)
		]

	def check_json_files(self):
		paths = [
			*self.list_own_files("sections", ".json"),
			*self.list_own_files("layouts", ".json"),
			*self.list_own_files("layouts/groups", ".json"),
		]
		if self.owns("settings.json"):
			paths.append("settings.json")
		for relative_path in paths:
			try:
				self.json_files[relative_path] = json.loads(self.read_text(relative_path))
			except ValueError as error:
				self.add(
					"invalid-json",
					relative_path,
					f"{relative_path} is not valid JSON: {getattr(error, 'msg', error)}",
					"Fix the JSON syntax; a trailing comma or a missing quote is the usual cause",
					getattr(error, "lineno", None),
				)

	def check_settings_file(self):
		if "settings.json" not in self.json_files:
			return
		data = self.json_files["settings.json"]
		if not self.is_object(data, "settings.json", "settings.json"):
			return
		self.check_unknown_keys(data, SETTINGS_FILE_KEYS, "settings.json", "settings.json")
		self.check_settings(data.get("settings", []), "settings.json", "theme settings")

	def get_own_section_types(self):
		return sorted(
			{
				os.path.splitext(os.path.basename(path))[0]
				for path in [
					*self.list_own_files("sections", ".json"),
					*self.list_own_files("sections", ".html"),
				]
			}
		)

	def check_section(self, section_type):
		json_path = f"sections/{section_type}.json"
		html_path = f"sections/{section_type}.html"
		if json_path in self.json_files:
			SectionSchemaChecker(self, section_type, json_path).check(self.json_files[json_path])
		if self.owns(json_path) and not find_theme_file(self.theme_dirs, html_path):
			self.add(
				"section-template-missing",
				json_path,
				f"{json_path} has no {html_path}",
				f"Add {html_path}, or run bench commera theme new-section to scaffold both files",
			)

		schema = get_section_schema(self.theme_dirs, section_type)
		html_file = find_theme_file(self.theme_dirs, html_path)
		if schema and html_file:
			template = Path(html_file).read_text()
			report_path = json_path if self.owns(json_path) else html_path
			SectionTemplateChecker(self, schema, html_path, report_path).check(template)

	def check_layouts(self):
		templates = [
			*[(path, os.path.basename(path)[:-5]) for path in self.list_own_files("layouts", ".json")],
			*[
				(path, GROUP_TEMPLATE_PREFIX + os.path.basename(path)[:-5])
				for path in self.list_own_files("layouts/groups", ".json")
			],
		]
		for relative_path, template in templates:
			if relative_path not in self.json_files:
				continue
			layout = self.json_files[relative_path]
			for rule, message in get_layout_findings(self.theme_dirs, template, layout, check_links=False):
				self.add(rule, relative_path, message, LAYOUT_FIXES[rule])

	def check_static_sections(self):
		for section_type, schema in get_section_schemas(self.theme_dirs).items():
			templates = schema.get("templates")
			if not schema.get("static") or not isinstance(templates, list):
				continue
			for template in templates:
				if template not in BASE_TEMPLATES:
					continue
				layout_path = get_layout_file(template)
				json_path = f"sections/{section_type}.json"
				if not (self.owns(layout_path) or self.owns(json_path)):
					continue
				sections = get_default_layout(self.theme_dirs, template).get("sections") or []
				if not any(
					isinstance(section, dict) and section.get("type") == section_type for section in sections
				):
					self.add(
						"static-section-missing",
						layout_path if self.owns(layout_path) else json_path,
						f'static section "{section_type}" is missing from {layout_path}',
						f'Add {{"id": "{section_type}", "type": "{section_type}"}} to the sections of {layout_path}',
					)

	def check_physical_css(self):
		for relative_path in [
			*self.list_own_files("sections", ".html"),
			*self.list_own_files("styles", ".css"),
		]:
			for line_number, line in enumerate(self.read_text(relative_path).splitlines(), start=1):
				for physical, logical in get_physical_properties(line):
					self.add(
						"physical-css-property",
						relative_path,
						f"{physical} breaks right-to-left pages; use {logical}",
						f"Replace {physical} with {logical}",
						line_number,
					)

	def check_pages(self):
		pages_dir = os.path.join(self.theme_dir, "pages")
		for root, _folders, filenames in os.walk(pages_dir):
			for filename in sorted(filenames):
				if filename.endswith(".html"):
					self.check_page(os.path.relpath(os.path.join(root, filename), self.theme_dir))

	def check_page(self, relative_path):
		for line_number, line in enumerate(self.read_text(relative_path).splitlines(), start=1):
			for match in RENDER_LAYOUT_PATTERN.finditer(line):
				layout_path = get_layout_file(match.group(1))
				if not find_theme_file(self.theme_dirs, layout_path):
					self.add(
						"template-without-layout",
						relative_path,
						f'render_layout("{match.group(1)}") has no {layout_path} in the theme or its parents',
						f'Add {layout_path} with {{"sections": []}} and the sections the page starts with',
						line_number,
					)


def get_physical_properties(line):
	for pattern, property_name in PHYSICAL_CSS_PATTERNS:
		for match in pattern.finditer(line):
			if property_name:
				side = match.group(1)
				yield f"{property_name}: {side}", f"{property_name}: {'start' if side == 'left' else 'end'}"
			elif match.lastindex == 1:
				yield match.group(1), f"inset-{LOGICAL_SIDES[match.group(1)]}"
			else:
				box, side, suffix = match.groups()
				yield f"{box}-{side}{suffix}", f"{box}-{LOGICAL_SIDES[side]}{suffix}"


def check_theme(theme_dirs):
	return ThemeChecker(theme_dirs).check()


def count_errors(findings):
	return sum(1 for finding in findings if finding["severity"] == ERROR)


def check_themes_on_disk(slug=None, apps_path=None):
	records = get_theme_records_on_disk(apps_path)
	if slug is not None and not os.path.isdir((records.get(slug) or {}).get("theme_dir", "")):
		raise click.UsageError(f"No theme folder with a Shop Theme record for {slug}; check the slug")

	findings = []
	for theme_slug in [slug] if slug else sorted(records):
		theme_dirs = get_theme_chain_dirs(records, theme_slug)
		if theme_dirs and theme_dirs[0] == records[theme_slug]["theme_dir"]:
			findings.extend({**finding, "theme": theme_slug} for finding in check_theme(theme_dirs))
	return findings


def print_theme_check_errors():
	try:
		for theme_name in frappe.get_all("Shop Theme", pluck="name"):
			theme_dirs = build_theme_context(theme_name)["dirs"]
			if not theme_dirs or os.path.basename(theme_dirs[0]) != frappe.scrub(theme_name):
				continue
			for finding in check_theme(theme_dirs):
				if finding["severity"] == ERROR:
					print(f"{theme_name} theme check: {format_location(finding)} {finding['message']}")
	except Exception:
		frappe.log_error(title="Theme check after migrate failed")


def format_location(finding, with_theme=True):
	location = finding["file"] + (f":{finding['line']}" if finding["line"] else "")
	return f"{finding['theme']}/{location}" if with_theme and finding.get("theme") else location


def format_findings(findings, with_theme=True):
	lines = []
	for finding in findings:
		lines.append(
			f"{format_location(finding, with_theme):<40} {finding['severity']:<8} {finding['message']}"
		)
	errors = count_errors(findings)
	warnings = len(findings) - errors
	lines.append(f"{errors} error{'s' * (errors != 1)}, {warnings} warning{'s' * (warnings != 1)}")
	return "\n".join(lines)
