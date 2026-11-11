# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""The dashboard's Translations page: status counts, records to translate, a batch save, and the CSV
exchange of one language. Shop-wide translations only; markets override through the CSV."""

import frappe
from frappe import _
from frappe.utils import cint, cstr

from commera.localization import exchange, translation_items
from commera.localization.content import DOCTYPE


@frappe.whitelist()
def get_overview() -> dict:
	"""Every target language with its missing, outdated and current counts per resource type."""
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)
	return translation_items.get_overview()


@frappe.whitelist()
def get_items(
	language: str,
	resource: str,
	to_do: int = 0,
	record: str | None = None,
	cursor: str | None = None,
	records: list | str | None = None,
) -> dict:
	"""One page of a resource's records with their fields, or selected records."""
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)
	return translation_items.get_items(
		language, resource, to_do=to_do, record=record, cursor=cursor, records=records
	)


@frappe.whitelist()
def search_translations(language: str, text: str) -> list[dict]:
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)
	return translation_items.search(language, text)


@frappe.whitelist(methods=["POST"])
def save_translations(language: str, translations: list | str) -> int:
	"""Write a batch of {resource, name, field, value}. Each resource checks its own write permission."""
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)
	return translation_items.save(language, translations)


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
	if cint(file.file_size) > exchange.MAX_FILE_SIZE:
		frappe.throw(_("The file is larger than {0} MB.").format(exchange.MAX_FILE_SIZE // (1024 * 1024)))
	return exchange.import_csv(file.get_content(), language).as_dict()
