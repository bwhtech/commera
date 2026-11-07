# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ShopifyRecordLink(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		reference_doctype: DF.Link
		reference_name: DF.DynamicLink
		resource: DF.Data | None
		shopify_id: DF.Data
		shopify_updated_at: DF.Datetime | None
	# end: auto-generated types

	pass


def get_link(shopify_id: str) -> dict | None:
	"""The Commera record a Shopify ID was imported into, when that record still exists."""
	link = frappe.db.get_value(
		"Shopify Record Link",
		{"shopify_id": shopify_id},
		["name", "reference_doctype", "reference_name", "shopify_updated_at"],
		as_dict=True,
	)
	if link and frappe.db.exists(link.reference_doctype, link.reference_name):
		return link
	return None


def get_linked_name(shopify_id: str) -> str | None:
	link = get_link(shopify_id)
	return link.reference_name if link else None


def save_link(
	shopify_id: str,
	resource: str,
	reference_doctype: str,
	reference_name: str,
	shopify_updated_at=None,
) -> None:
	values = {
		"resource": resource,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"shopify_updated_at": shopify_updated_at,
	}
	name = frappe.db.get_value("Shopify Record Link", {"shopify_id": shopify_id})
	if name:
		frappe.db.set_value("Shopify Record Link", name, values)
		return

	link = frappe.new_doc("Shopify Record Link")
	link.shopify_id = shopify_id
	link.update(values)
	link.insert(ignore_permissions=True)
