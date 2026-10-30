import frappe
from frappe.tests import IntegrationTestCase

from commera.customizations import (
	MODULES,
	create_customizations,
	delete_customizations,
	get_fields_by_doctype,
)


def get_present_fields() -> set[tuple[str, str]]:
	return {
		(doctype, field["fieldname"])
		for module in MODULES
		for doctype, fields in get_fields_by_doctype(module.CUSTOM_FIELDS).items()
		for field in fields
		if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field["fieldname"]})
	}


def get_present_setters() -> list[dict]:
	return [
		setter
		for module in MODULES
		for setter in module.PROPERTY_SETTERS
		if frappe.db.get_value(
			"Property Setter",
			{
				"doc_type": setter["doctype"],
				"field_name": setter["fieldname"],
				"property": setter["property"],
			},
			"value",
		)
		== setter["value"]
	]


def has_payment_request_link() -> bool:
	return bool(
		frappe.db.exists("DocType Link", {"parent": "Sales Order", "link_doctype": "Gateway Payment Request"})
	)


class TestCustomizations(IntegrationTestCase):
	"""Commera's Custom Fields, Property Setters and Sales Order links come from Python and leave with the app."""

	def test_setup_creates_every_field_and_setter_and_is_repeatable(self):
		create_customizations()
		create_customizations()

		self.assertEqual(
			get_present_fields(),
			{
				(doctype, field["fieldname"])
				for m in MODULES
				for doctype, fields in get_fields_by_doctype(m.CUSTOM_FIELDS).items()
				for field in fields
			},
		)
		self.assertEqual(len(get_present_setters()), sum(len(m.PROPERTY_SETTERS) for m in MODULES))
		self.assertTrue(frappe.get_meta("Shipment").get_field("custom_sales_order"))
		self.assertTrue(has_payment_request_link())

	def test_uninstall_removes_every_field_and_setter(self):
		# Custom Field changes run DDL, which commits, so restore and commit instead of rolling back.
		self.addCleanup(frappe.db.commit)
		self.addCleanup(create_customizations)

		delete_customizations()

		self.assertEqual(get_present_fields(), set())
		self.assertEqual(get_present_setters(), [])
		self.assertFalse(frappe.get_meta("Shipment").get_field("custom_sales_order"))
		self.assertFalse(has_payment_request_link())
