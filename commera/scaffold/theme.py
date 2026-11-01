import io
from contextlib import redirect_stdout
from pathlib import Path

import click
import frappe
from frappe.modules.export_file import write_document_file
from frappe.utils import strip_html

from commera.scaffold import AppScaffold
from commera.shop_themes.doctype.shop_theme.shop_theme import (
	DEFAULT_THEME_APP,
	DEFAULT_THEME_MODULE,
	copy_starter_settings_doctype,
	get_theme_export_dir,
	scaffold_theme,
	validate_theme_name,
)


class ThemeScaffold(AppScaffold):
	allow_host_app = True

	def get_theme_module(self) -> str:
		if self.app == DEFAULT_THEME_APP:
			return DEFAULT_THEME_MODULE
		return frappe.get_module_list(self.app)[0]

	def get_relative_path(self, path: Path) -> str:
		return str(path.relative_to(Path(frappe.get_app_path(self.app)).parent))

	def is_installed(self) -> bool:
		return self.app in frappe.get_installed_apps()

	def add_theme(self, theme_name: str, theme_type: str, parent_theme: str | None) -> list[tuple[str, str]]:
		if frappe.db.exists("Shop Theme", theme_name):
			raise click.ClickException(f"Shop Theme {theme_name} already exists; pick another name")

		theme = frappe.new_doc("Shop Theme")
		theme.update(
			{
				"theme_name": theme_name,
				"theme_type": theme_type,
				"parent_theme": parent_theme,
				"module": self.get_theme_module(),
				"is_standard": 1,
			}
		)
		developer_mode = frappe.conf.developer_mode
		frappe.conf.developer_mode = 1
		try:
			if self.is_installed():
				self.insert_theme(theme)
			else:
				self.write_theme_files(theme)
		except frappe.ValidationError as error:
			raise click.ClickException(strip_html(str(error)))
		finally:
			frappe.conf.developer_mode = developer_mode

		slug = frappe.scrub(theme_name)
		export_path = Path(get_theme_export_dir(theme.module, slug), f"{slug}.json")
		if export_path.exists():
			self.changes.append(("created", self.get_relative_path(export_path)))
		return self.changes

	def insert_theme(self, theme):
		theme.flags.scaffold = True
		theme.insert()
		self.changes.extend(theme.flags.scaffold_changes)

	def write_theme_files(self, theme):
		validate_theme_name(theme.theme_name)
		theme.validate_unique_slug()
		if theme.parent_theme:
			if not frappe.db.exists("Shop Theme", theme.parent_theme):
				frappe.throw(
					frappe._("Shop Theme {0} does not exist on this site").format(theme.parent_theme)
				)
			theme.validate_parent_theme_type()

		theme.name = theme.theme_name
		self.changes.extend(
			scaffold_theme(
				theme.theme_name,
				theme.module,
				theme.theme_type,
				app=self.app,
				parent_theme=theme.parent_theme,
			)
		)
		with redirect_stdout(io.StringIO()):
			if theme.copies_starter():
				theme.theme_settings = self.write_settings_doctype_files(theme)
			write_document_file(theme, record_module=theme.module)

	def write_settings_doctype_files(self, theme) -> str:
		settings_doctype = copy_starter_settings_doctype(f"{theme.theme_name} Settings", theme.module)
		settings_doctype.set("__islocal", None)
		write_document_file(settings_doctype, record_module=theme.module)
		settings_doctype.make_controller_template()
		self.changes.append(
			(
				"created",
				self.get_relative_path(
					Path(frappe.get_module_path(theme.module), "doctype", frappe.scrub(settings_doctype.name))
				),
			)
		)
		return settings_doctype.name
