import frappe
from frappe import _
from frappe.model.document import Document

from commera.shop_themes.doctype.shop_theme.shop_theme import build_theme_context
from commera.shop_themes.sections import clear_layout_cache, validate_layout


class ThemeLayout(Document):
	def validate(self):
		if not self.page.replace("_", "").replace("-", "").isalnum():
			frappe.throw(_("Page must hold only letters, digits, - and _."))

		theme_context = build_theme_context(self.theme)
		for fieldname in ("draft_layout", "published_layout"):
			if self.get(fieldname):
				validate_layout(theme_context, frappe.parse_json(self.get(fieldname)), self.page)

	def on_update(self):
		clear_layout_cache(self.theme, self.page)

	def on_trash(self):
		clear_layout_cache(self.theme, self.page)

	@frappe.whitelist()
	def publish(self):
		frappe.only_for(("Website Manager", "System Manager"))
		if not self.draft_layout:
			frappe.throw(_("There is no draft to publish."))
		self.published_layout = self.draft_layout
		self.save()
