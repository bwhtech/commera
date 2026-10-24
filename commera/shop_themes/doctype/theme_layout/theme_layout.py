# Copyright (c) 2026, BWH Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from commera.shop_themes.doctype.shop_theme.shop_theme import get_theme_context
from commera.shop_themes.layouts import TEMPLATE_PATTERN, clear_layout_cache, validate_layout


class ThemeLayout(Document):
	def validate(self):
		if not TEMPLATE_PATTERN.match(self.template or ""):
			frappe.throw(_("{0} is not a layout template").format(self.template))
		self.validate_unique_template()
		self.is_synced_from_settings = 1 if self.flags.synced_from_settings else 0

		theme_dirs = get_theme_context(self.theme)["dirs"]
		self.validate_layout_field("layout", theme_dirs)
		if self.has_value_changed("published_layout"):
			self.validate_layout_field("published_layout", theme_dirs)

	def validate_unique_template(self):
		filters = {"theme": self.theme, "template": self.template, "name": ("!=", self.name or "")}
		if frappe.db.exists("Theme Layout", filters):
			frappe.throw(
				_("Theme {0} already has a layout for {1}").format(self.theme, self.template),
				frappe.DuplicateEntryError,
			)

	def validate_layout_field(self, fieldname, theme_dirs):
		value = self.get(fieldname)
		if not value:
			return
		try:
			layout = frappe.parse_json(value)
		except ValueError:
			frappe.throw(_("{0} is not valid JSON").format(self.meta.get_label(fieldname)))

		errors = validate_layout(theme_dirs, self.template, layout)
		if errors:
			frappe.throw(errors, title=_("Invalid {0}").format(self.meta.get_label(fieldname)), as_list=True)

	def publish(self):
		self.published_layout = self.layout
		self.published_on = now_datetime()
		self.published_by = frappe.session.user
		self.save()

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


def on_doctype_update():
	frappe.db.add_unique("Theme Layout", ["theme", "template"], constraint_name="unique_theme_template")
