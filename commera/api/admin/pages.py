# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.utils.data import cint, cstr

from commera.commera_ecommerce.doctype.commera_settings.editor_input import require_value

PAGE_DOCTYPE = "Shop Web Page"

# The only fields the dashboard may write. Anything else in the payload is ignored, so the
# editor can never reach owner, docstatus or a field a later version of the DocType adds.
EDITABLE_FIELDS = (
	"route",
	"published",
	"content",
	"meta_title",
	"meta_description",
	"og_image",
	"noindex",
)

CHECK_FIELDS = ("published", "noindex")


def get_page_url(route: str | None) -> str | None:
	return f"/en/page/{cstr(route)}" if route else None


@frappe.whitelist()
def get_pages(search: str | None = None) -> dict:
	"""The Pages list screen in one call."""
	frappe.has_permission(PAGE_DOCTYPE, ptype="read", throw=True)

	or_filters = None
	if search:
		pattern = f"%{cstr(search)}%"
		or_filters = [["name", "like", pattern], ["route", "like", pattern]]

	# ponytail: the whole list comes back unpaged and the dashboard pages it client-side,
	# as the mock did; add start/page_length once a store keeps more than a screenful of pages
	pages = frappe.get_all(
		PAGE_DOCTYPE,
		or_filters=or_filters,
		fields=["name", "route", "published", "modified"],
		order_by="modified desc",
	)

	return {
		"pages": [
			{
				"name": row.name,
				"route": row.route,
				"url": get_page_url(row.route),
				"published": cint(row.published),
				"modified": row.modified,
			}
			for row in pages
		],
		"total": len(pages),
	}


@frappe.whitelist()
def get_page(name: str) -> dict:
	"""Every field the page editor binds to."""
	frappe.has_permission(PAGE_DOCTYPE, ptype="read", throw=True)

	page = frappe.get_doc(PAGE_DOCTYPE, name)

	return {
		"name": cstr(page.name),
		"route": page.route,
		"url": get_page_url(page.route),
		"published": cint(page.published),
		"content": page.content,
		"meta_title": page.meta_title,
		"meta_description": page.meta_description,
		"og_image": page.og_image,
		"noindex": cint(page.noindex),
		"modified": page.modified,
	}


@frappe.whitelist(methods=["POST"])
def save_page(name: str | None = None, **fields) -> dict:
	"""Create a page, or update the one called `name`. Returns it in get_page's shape."""
	frappe.has_permission(PAGE_DOCTYPE, ptype="write", throw=True)

	title = cstr(fields.get("title") or "").strip()

	if name:
		page = frappe.get_doc(PAGE_DOCTYPE, name)
		# The doc name IS the page title, so retitling is a rename. The route is left alone:
		# it was published under the old title and renaming must not break the live link.
		if title and title != cstr(page.name):
			frappe.rename_doc(PAGE_DOCTYPE, page.name, title)
			page = frappe.get_doc(PAGE_DOCTYPE, title)
	else:
		page = frappe.new_doc(PAGE_DOCTYPE)
		page.name = require_value(title, frappe._("Page title is required."))

	for fieldname in EDITABLE_FIELDS:
		if fieldname not in fields:
			continue
		value = fields[fieldname]
		page.set(fieldname, cint(value) if fieldname in CHECK_FIELDS else value)

	page.save()

	return get_page(page.name)


@frappe.whitelist(methods=["POST"])
def delete_page(name: str) -> None:
	frappe.has_permission(PAGE_DOCTYPE, ptype="delete", throw=True)

	frappe.delete_doc(PAGE_DOCTYPE, name)
