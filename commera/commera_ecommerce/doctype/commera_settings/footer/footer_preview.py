# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe

from commera.api.admin.pages import PAGE_DOCTYPE, get_page_url
from commera.commera_ecommerce.doctype.commera_settings.editor_input import (
	parse_list,
	require_safe_url,
	require_value,
)
from commera.localization.content import move_translations

# Storefront pages come from hooks.website_route_rules, not Web Page docs, so the picker cannot see them.
# Routes needing a query param or a cart (checkout, confirmation, order detail) are deliberately absent.
STATIC_STOREFRONT_ROUTES = (
	("Home", "/en"),
	("Products", "/en/products"),
	("Cart", "/en/cart"),
	("My Account", "/en/account/dashboard"),
	("Orders", "/en/account/orders"),
	("Wishlist", "/en/account/wishlist"),
	("Addresses", "/en/account/address"),
	("Profile", "/en/account/profile"),
)


@frappe.whitelist()
def get_footer_editor_data():
	frappe.has_permission("Commera Settings", "read", throw=True)
	settings = frappe.get_single("Commera Settings")
	mapping_rows = sorted(settings.footer_sections, key=lambda row: row.section_order or 0)
	section_names = [row.footer_section for row in mapping_rows]

	section_titles = {}
	if section_names:
		for row in frappe.get_all(
			"Footer Section Config",
			filters={"name": ["in", section_names]},
			fields=["name", "section_title"],
		):
			section_titles[row.name] = row.section_title

	links_by_section = {}
	if section_names:
		for row in frappe.get_all(
			"Footer Link",
			filters={"parent": ["in", section_names], "parenttype": "Footer Section Config"},
			fields=["name", "parent", "link_label", "link_url", "link_order", "enabled"],
			order_by="link_order asc",
		):
			links_by_section.setdefault(row.parent, []).append(row)

	columns = []
	for mapping_row in mapping_rows:
		title = section_titles.get(mapping_row.footer_section)
		if not title:
			continue
		columns.append(
			{
				"name": mapping_row.footer_section,
				"title": title,
				"section_order": mapping_row.section_order,
				"enabled": mapping_row.enabled,
				"links": links_by_section.get(mapping_row.footer_section, []),
			}
		)

	# Shop Web Page, not Web Page: a core Web Page renders outside the storefront theme, so offering
	# one in the footer would drop the shopper out of the shop.
	pages = [
		{"name": page.name, "route": get_page_url(page.route)}
		for page in frappe.get_all(
			PAGE_DOCTYPE, filters={"published": 1}, fields=["name", "route"], order_by="name asc"
		)
		if page.route
	]
	pages += [{"name": label, "route": route} for label, route in STATIC_STOREFRONT_ROUTES]

	return {
		"columns": columns,
		"pages": pages,
		"modified": settings.modified,
	}


@frappe.whitelist(methods=["POST"])
def add_footer_section(title: str):
	frappe.has_permission("Commera Settings", "write", throw=True)

	title = require_value(title, frappe._("Column title is required."))

	# Map on name, not the typed title: get_footer_editor_data silently skips a mapping whose doc is missing.
	section = frappe.get_doc({"doctype": "Footer Section Config", "section_title": title}).insert()

	settings = frappe.get_single("Commera Settings")
	next_order = max([row.section_order or 0 for row in settings.footer_sections], default=0) + 1
	settings.append(
		"footer_sections", {"footer_section": section.name, "section_order": next_order, "enabled": 1}
	)
	settings.save()

	return get_footer_editor_data()


@frappe.whitelist(methods=["POST"])
def rename_footer_section(old_name: str, new_name: str):
	frappe.has_permission("Commera Settings", "write", throw=True)

	new_name = require_value(new_name, frappe._("Column title is required."))

	frappe.rename_doc("Footer Section Config", old_name, new_name)

	return get_footer_editor_data()


@frappe.whitelist(methods=["POST"])
def delete_footer_section(name: str):
	frappe.has_permission("Commera Settings", "write", throw=True)

	settings = frappe.get_single("Commera Settings")
	if not any(row.footer_section == name for row in settings.footer_sections):
		frappe.throw(frappe._("Footer section {0} is not part of this footer.").format(name))

	settings.footer_sections = [row for row in settings.footer_sections if row.footer_section != name]
	settings.save()

	frappe.delete_doc("Footer Section Config", name)

	return get_footer_editor_data()


@frappe.whitelist(methods=["POST"])
def reorder_footer_sections(ordered_names: list[str] | str):
	frappe.has_permission("Commera Settings", "write", throw=True)

	ordered_names = parse_list(ordered_names)

	settings = frappe.get_single("Commera Settings")
	rows_by_section = {row.footer_section: row for row in settings.footer_sections}

	missing = [name for name in ordered_names if name not in rows_by_section]
	if missing:
		frappe.throw(frappe._("Unknown footer section(s): {0}").format(", ".join(missing)))

	for index, section_name in enumerate(ordered_names, start=1):
		rows_by_section[section_name].section_order = index
	settings.save()

	return get_footer_editor_data()


@frappe.whitelist(methods=["POST"])
def add_footer_link(section_name: str, label: str, url: str):
	frappe.has_permission("Commera Settings", "write", throw=True)

	label = require_value(label, frappe._("Link label is required."))
	url = require_safe_url(url, frappe._("Link URL is required."))

	section = frappe.get_doc("Footer Section Config", section_name)
	next_order = max([row.link_order or 0 for row in section.footer_links], default=0) + 1
	section.append(
		"footer_links", {"link_label": label, "link_url": url, "link_order": next_order, "enabled": 1}
	)
	section.save()

	return get_footer_editor_data()


@frappe.whitelist(methods=["POST"])
def update_footer_link(section_name: str, link_row_name: str, label: str, url: str):
	frappe.has_permission("Commera Settings", "write", throw=True)

	label = require_value(label, frappe._("Link label is required."))
	url = require_safe_url(url, frappe._("Link URL is required."))

	section = frappe.get_doc("Footer Section Config", section_name)
	row = next((link_row for link_row in section.footer_links if link_row.name == link_row_name), None)
	if not row:
		frappe.throw(frappe._("Link not found in {0}.").format(section_name))

	row.link_label = label
	row.link_url = url
	section.save()

	return get_footer_editor_data()


@frappe.whitelist(methods=["POST"])
def delete_footer_link(section_name: str, link_row_name: str):
	frappe.has_permission("Commera Settings", "write", throw=True)

	section = frappe.get_doc("Footer Section Config", section_name)
	section.footer_links = [row for row in section.footer_links if row.name != link_row_name]
	section.save()

	return get_footer_editor_data()


@frappe.whitelist(methods=["POST"])
def reorder_footer_links(section_name: str, ordered_row_names: list[str] | str):
	frappe.has_permission("Commera Settings", "write", throw=True)

	ordered_row_names = parse_list(ordered_row_names)

	section = frappe.get_doc("Footer Section Config", section_name)
	rows_by_name = {row.name: row for row in section.footer_links}

	missing = [name for name in ordered_row_names if name not in rows_by_name]
	if missing:
		frappe.throw(frappe._("Unknown footer link row(s): {0}").format(", ".join(missing)))

	for index, row_name in enumerate(ordered_row_names, start=1):
		row = rows_by_name[row_name]
		row.link_order = index
		row.idx = index
	section.save()

	return get_footer_editor_data()


@frappe.whitelist(methods=["POST"])
def move_footer_link(from_section: str, to_section: str, link_row_name: str, target_index: int):
	frappe.has_permission("Commera Settings", "write", throw=True)

	target_index = frappe.utils.cint(target_index)

	source = frappe.get_doc("Footer Section Config", from_section)
	source_links = sorted(source.footer_links, key=lambda row: row.link_order or 0)
	row = next((link_row for link_row in source_links if link_row.name == link_row_name), None)
	if not row:
		frappe.throw(frappe._("Link not found in {0}.").format(from_section))
	label, url, enabled = row.link_label, row.link_url, row.enabled

	remaining = [link_row for link_row in source_links if link_row.name != link_row_name]
	for index, remaining_row in enumerate(remaining, start=1):
		remaining_row.link_order = index
		remaining_row.idx = index
	source.footer_links = remaining
	source.save()

	target = frappe.get_doc("Footer Section Config", to_section)
	existing_target_links = sorted(target.footer_links, key=lambda row: row.link_order or 0)
	new_row = target.append("footer_links", {"link_label": label, "link_url": url, "enabled": enabled})
	target_index = max(0, min(target_index, len(existing_target_links)))
	existing_target_links.insert(target_index, new_row)
	target.footer_links = existing_target_links
	for index, target_row in enumerate(target.footer_links, start=1):
		target_row.link_order = index
		target_row.idx = index
	target.save()
	# The moved link is a new row, so its translations follow it there.
	move_translations("Footer Link", link_row_name, new_row.name)

	return get_footer_editor_data()
