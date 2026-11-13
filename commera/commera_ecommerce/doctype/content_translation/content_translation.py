# Copyright (c) 2026, hussain@buildwithhussain.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from commera.localization.content import get_market_key, get_source_hash, get_source_text, read_source
from commera.localization.resources import get_translatable_fields

KEY_FIELDS = ["reference_doctype", "reference_name", "reference_field", "language", "market"]


class ContentTranslation(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		language: DF.Link
		market: DF.Data
		reference_doctype: DF.Link
		reference_field: DF.Data
		reference_name: DF.Data
		source_hash: DF.Data | None
		source_text: DF.SmallText | None
		translated_value: DF.LongText | None
	# end: auto-generated types

	def validate(self):
		self.market = get_market_key(self.market)
		if not frappe.db.exists(self.reference_doctype, self.reference_name):
			frappe.throw(_("The translation source does not exist."), frappe.LinkValidationError)
		if self.reference_field not in get_translatable_fields(self.reference_doctype):
			frappe.throw(
				_("{0} of {1} is not a translatable field.").format(
					frappe.bold(self.reference_field), frappe.bold(_(self.reference_doctype))
				)
			)
		if self.flags.refresh_source_hash or self.source_changed():
			source = read_source(self.reference_doctype, self.reference_name, self.reference_field)
			self.source_hash = get_source_hash(source)
			if frappe.db.has_column("Content Translation", "source_text"):
				self.source_text = get_source_text(self.reference_doctype, self.reference_field, source)

	def source_changed(self) -> bool:
		"""A new or edited translation was written against the source as it is now."""
		return self.is_new() or any(
			self.has_value_changed(field)
			for field in ("translated_value", "reference_doctype", "reference_name", "reference_field")
		)


def on_doctype_update():
	frappe.db.add_unique("Content Translation", KEY_FIELDS, constraint_name="unique_content_translation")
