# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""Translation exchange for the dashboard: download one language as CSV, upload one back."""

import frappe
from frappe import _
from frappe.utils import cint, cstr

from commera.localization import exchange
from commera.localization.content import DOCTYPE

MAX_FILE_SIZE = 10 * 1024 * 1024


@frappe.whitelist(methods=["GET"])
def export_translations(language: str):
	"""A CSV download of `language`'s translations, Shopify's columns."""
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)
	content = exchange.export_csv(language)
	frappe.response.update(
		{
			"type": "download",
			"filename": f"translations-{cstr(language).lower()}.csv",
			# The byte order mark makes Excel read the file as UTF-8, so Arabic stays readable.
			"filecontent": "﻿" + content,
			"content_type": "text/csv; charset=utf-8",
		}
	)


@frappe.whitelist(methods=["POST"])
def import_translations(file_url: str, language: str) -> dict:
	"""Write an uploaded CSV's translations of `language`. Answers a report with an error per bad row."""
	frappe.has_permission(DOCTYPE, ptype="write", throw=True)
	frappe.has_permission(DOCTYPE, ptype="create", throw=True)
	file = frappe.get_doc("File", {"file_url": file_url})
	file.check_permission("read")
	if not cstr(file.file_name).lower().endswith(".csv"):
		frappe.throw(_("Upload a CSV file."))
	if cint(file.file_size) > MAX_FILE_SIZE:
		frappe.throw(_("The file is larger than {0} MB.").format(MAX_FILE_SIZE // (1024 * 1024)))
	return exchange.import_csv(file.get_content(), language).as_dict()
