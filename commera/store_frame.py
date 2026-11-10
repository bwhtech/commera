# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""The storefront frame in the request language: the shop name and description, and the footer.
Link URLs stay as the merchant entered them."""

import frappe
from frappe.utils import cstr

from commera.localization import Localization, translate

SETTINGS = "Commera Settings"
SECTION_DOCTYPE = "Footer Section Config"
LINK_DOCTYPE = "Footer Link"
SHOP_KEYS = {"name": "store_name", "description": "default_meta_description"}
SHOP_FIELDS = list(SHOP_KEYS.values())


def get_shop_details(localization: Localization | None = None) -> frappe._dict:
	"""The store `name` and `description`, translated. Either is blank when the merchant left it blank."""
	settings = frappe.get_cached_doc(SETTINGS)
	# A Single's translations name the doctype itself as the record.
	record = {"name": SETTINGS, **{field: settings.get(field) for field in SHOP_FIELDS}}
	fields = translate([record], SHOP_FIELDS, localization, doctype=SETTINGS)[0]
	return frappe._dict({key: fields[field].value for key, field in SHOP_KEYS.items()})


def get_preview_shop_details(preview_settings, localization: Localization) -> frappe._dict:
	"""get_shop_details() for an editor preview: a field with an unsaved edit shows the edit as typed."""
	details = get_shop_details(localization)
	saved = frappe.get_cached_doc(SETTINGS)
	for key, field in SHOP_KEYS.items():
		if cstr(preview_settings.get(field)) != cstr(saved.get(field)):
			details[key] = preview_settings.get(field)
	return details


def get_storefront_footer(localization: Localization | None = None) -> list[frappe._dict]:
	"""The footer's enabled sections in order, each with its enabled links in order, translated."""
	sections = [build_section(row.footer_section) for row in get_footer_rows()]
	links = [link for section in sections for link in section.links]
	translate_titles(sections, "section_title", SECTION_DOCTYPE, localization)
	translate_titles(links, "link_label", LINK_DOCTYPE, localization)
	return sections


def get_footer_rows() -> list:
	settings = frappe.get_cached_doc(SETTINGS)
	rows = [row for row in settings.footer_sections or [] if row.enabled]
	return sorted(rows, key=lambda row: row.section_order or 0)


def build_section(name: str) -> frappe._dict:
	section = frappe.get_cached_doc(SECTION_DOCTYPE, name)
	links = sorted(
		(link for link in section.footer_links if link.enabled), key=lambda link: link.link_order or 0
	)
	return frappe._dict(
		name=section.name,
		title=section.section_title,
		enabled=section.enabled,
		links=[frappe._dict(name=link.name, title=link.link_label, url=link.link_url) for link in links],
	)


def translate_titles(entries: list, field: str, doctype: str, localization: Localization | None):
	"""Set each entry's `title` to its translated `field`, in one lookup for all entries."""
	records = [{"name": entry.name, field: entry.title} for entry in entries]
	for entry, fields in zip(entries, translate(records, [field], localization, doctype), strict=True):
		entry.title = fields[field].value
