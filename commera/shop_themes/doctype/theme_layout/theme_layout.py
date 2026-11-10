import frappe
from frappe import _
from frappe.model.document import Document

from commera.shop_themes.doctype.shop_theme.shop_theme import build_theme_context
from commera.shop_themes.layout_cache import cache_layout_on_commit
from commera.shop_themes.section_text import is_overlay
from commera.shop_themes.section_text_checks import prepare_theme_layout
from commera.shop_themes.sections import validate_layout


class ThemeLayout(Document):
	def validate(self):
		if not self.page.replace("_", "").replace("-", "").isalnum():
			frappe.throw(_("Page must hold only letters, digits, - and _."))

		theme_context = build_theme_context(self.theme)
		for fieldname in ("draft_layout", "published_layout"):
			layout = frappe.parse_json(self.get(fieldname)) if self.get(fieldname) else None
			# A live translation overlay has no sections; prepare_theme_layout checks it.
			if layout is not None and not (fieldname == "published_layout" and is_overlay(layout)):
				validate_layout(theme_context, layout, self.page)
		prepare_theme_layout(self, theme_context)

	def on_update(self):
		cache_layout_on_commit(self.theme, self.page, self.published_layout)

	def on_trash(self):
		cache_layout_on_commit(self.theme, self.page, None)

	@frappe.whitelist()
	def publish(self):
		frappe.only_for(("Website Manager", "System Manager"))
		if not self.draft_layout:
			frappe.throw(_("There is no draft to publish."))
		# The draft's source hashes go live with it, replacing the live ones and any translation overlay.
		self.published_layout = self.draft_layout
		self.save()
