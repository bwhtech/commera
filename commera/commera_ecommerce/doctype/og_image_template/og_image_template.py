# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class OGImageTemplate(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		enabled: DF.Check
		for_doctype: DF.Link
		preview_image: DF.AttachImage | None
		template_html: DF.Code
	# end: auto-generated types

	def before_insert(self):
		if not self.template_html:
			card_path = frappe.get_app_path("commera", "templates", "og", "product_card.html")
			# nosemgrep: frappe-security-file-traversal  # hardcoded bundled app path, not user-controlled
			with open(card_path) as card_file:
				self.template_html = card_file.read()

	@frappe.whitelist()
	def generate_preview(self):
		from frappe.utils.file_manager import save_file

		from commera.og import generator

		# Defense in depth on the Jinja (SSTI) sink, independent of doctype perms.
		frappe.only_for("System Manager")

		sample = frappe.get_all(self.for_doctype, filters={"is_published": 1}, limit=1) or frappe.get_all(
			self.for_doctype, limit=1
		)
		if not sample:
			frappe.throw(f"No {self.for_doctype} records exist to preview this template against.")

		sample_doc = frappe.get_cached_doc(self.for_doctype, sample[0].name)
		jpeg_bytes = generator.render_card_for_doc(self.for_doctype, sample_doc)

		if self.preview_image:
			prior = frappe.db.get_value(
				"File",
				{
					"file_url": self.preview_image,
					"attached_to_doctype": self.doctype,
					"attached_to_name": self.name,
				},
			)
			if prior:
				# Clear the link first: File deletion throws LinkExistsError while a field points at it.
				self.db_set("preview_image", None)
				frappe.delete_doc("File", prior, ignore_permissions=True)

		preview_file = save_file(
			f"og-preview-{frappe.scrub(self.name)}.jpg",
			jpeg_bytes,
			self.doctype,
			self.name,
			df="preview_image",
			is_private=0,
		)
		# db_set, not save(): a full save() re-runs attachment handling and creates a second File.
		self.db_set("preview_image", preview_file.file_url)

		return preview_file.file_url
