import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields, delete_custom_fields
from frappe.custom.doctype.property_setter.property_setter import (
	bulk_delete_property_setters,
	make_property_setter,
)

from commera.commera_ecommerce import customizations as ecommerce
from commera.shipping import customizations as shipping

MODULES = (ecommerce, shipping)
# Connections on the Sales Order dashboard, added only when the payment app is installed.
SALES_ORDER_LINKS = {"Gateway Payment Request": "ref_docname", "Tabby Payment Request": "ref_docname"}


def create_customizations():
	"""Create or update Commera's Custom Fields, Property Setters and Sales Order connections."""
	for module in MODULES:
		create_custom_fields(module.CUSTOM_FIELDS)
		for setter in module.PROPERTY_SETTERS:
			create_property_setter(setter)

	for link_doctype, link_fieldname in SALES_ORDER_LINKS.items():
		add_sales_order_link(link_doctype, link_fieldname)


def delete_customizations():
	"""Remove everything create_customizations adds. Frappe keeps the columns and their data."""
	for module in MODULES:
		delete_custom_fields(get_fields_by_doctype(module.CUSTOM_FIELDS))
		bulk_delete_property_setters(
			[
				{key: setter[key] for key in ("doctype", "fieldname", "property")}
				for setter in module.PROPERTY_SETTERS
			]
		)

	frappe.db.delete(
		"DocType Link",
		{"parent": "Sales Order", "custom": 1, "link_doctype": ("in", list(SALES_ORDER_LINKS))},
	)
	frappe.clear_cache(doctype="Sales Order")


def get_fields_by_doctype(custom_fields: dict) -> dict[str, list[dict]]:
	"""Expand the tuple keys create_custom_fields accepts, which delete_custom_fields does not."""
	fields_by_doctype = {}
	for doctypes, fields in custom_fields.items():
		for doctype in (doctypes,) if isinstance(doctypes, str) else doctypes:
			fields_by_doctype.setdefault(doctype, []).extend(fields)
	return fields_by_doctype


def create_property_setter(setter: dict):
	filters = {
		"doc_type": setter["doctype"],
		"field_name": setter["fieldname"],
		"property": setter["property"],
	}
	if frappe.db.get_value("Property Setter", filters, "value") == setter["value"]:
		return

	make_property_setter(**setter, validate_fields_for_doctype=False)


def add_sales_order_link(link_doctype: str, link_fieldname: str):
	filters = {"parent": "Sales Order", "link_doctype": link_doctype}
	if not frappe.db.exists("DocType", link_doctype) or frappe.db.exists("DocType Link", filters):
		return

	link = frappe.get_doc(
		{
			"doctype": "DocType Link",
			"parent": "Sales Order",
			"parenttype": "DocType",
			"parentfield": "links",
			"link_doctype": link_doctype,
			"link_fieldname": link_fieldname,
			"custom": 1,
		}
	)
	link.db_insert()
	frappe.clear_cache(doctype="Sales Order")
