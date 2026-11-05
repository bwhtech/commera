from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.patches.move_shipping_requests_to_shipment import OLD_DOCTYPES, execute
from commera.sdk import STORE_ORDER_TYPE
from commera.shipping.tests.test_carrier_import import create_test_address, create_test_provider_profile
from commera.tests.test_admin_orders import make_test_sales_order

REQUEST_FIELDS = {
	"Data": (
		"provider",
		"shipping_service",
		"service_code",
		"carrier",
		"status",
		"provider_status",
		"company",
		"ref_doctype",
		"ref_docname",
		"delivery_note",
		"origin_address",
		"destination_address",
		"currency",
		"cost_currency",
		"order_ref",
		"shipment_ref",
		"awb",
		"tracking_ref",
		"pickup_ref",
		"last_webhook_event_id",
	),
	"Small Text": ("label_url", "manifest_url"),
	"Currency": ("declared_value", "cod_amount", "cost_amount"),
	"Check": ("cod",),
	"Date": ("pickup_date",),
}


def create_old_doctypes():
	frappe.get_doc(
		{
			"doctype": "DocType",
			"name": "Shipping Parcel",
			"module": "Shipping",
			"custom": 1,
			"istable": 1,
			"fields": [
				{"fieldname": fieldname, "fieldtype": "Int" if fieldname == "count" else "Float"}
				for fieldname in ("length", "width", "height", "weight", "count")
			],
		}
	).insert()
	fields = [
		{"fieldname": fieldname, "fieldtype": fieldtype}
		for fieldtype, fieldnames in REQUEST_FIELDS.items()
		for fieldname in fieldnames
	]
	fields.append({"fieldname": "parcels", "fieldtype": "Table", "options": "Shipping Parcel"})
	frappe.get_doc(
		{
			"doctype": "DocType",
			"name": "Shipping Request",
			"module": "Shipping",
			"custom": 1,
			"autoname": "hash",
			"permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1}],
			"fields": fields,
		}
	).insert()


def delete_old_doctypes():
	for doctype in OLD_DOCTYPES:
		frappe.delete_doc("DocType", doctype, force=True, ignore_missing=True)
		frappe.db.sql_ddl(f"drop table if exists `tab{doctype}`")


class TestMoveShippingRequests(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		delete_old_doctypes()
		create_old_doctypes()
		cls.addClassCleanup(delete_old_doctypes)

	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.delete_doc = self.enterContext(
			patch("commera.patches.move_shipping_requests_to_shipment.frappe.delete_doc")
		)
		self.sql_ddl = self.enterContext(
			patch("commera.patches.move_shipping_requests_to_shipment.frappe.db.sql_ddl")
		)
		self.provider = create_test_provider_profile()
		sales_order = make_test_sales_order(order_type=STORE_ORDER_TYPE)
		self.company_address = create_test_address("India", "Company", sales_order.company)
		sales_order.db_set("company_address", self.company_address)
		self.sales_order = sales_order
		self.delivery_address = create_test_address("India", "Customer", sales_order.customer)

	def make_request(self, **fields):
		request = frappe.get_doc(
			{
				"doctype": "Shipping Request",
				"provider": self.provider,
				"company": self.sales_order.company,
				"ref_doctype": "Sales Order",
				"ref_docname": self.sales_order.name,
				"destination_address": self.delivery_address,
				"currency": "INR",
				"declared_value": 1200,
				**fields,
			}
		).insert()
		return request.name

	def make_booked_request(self):
		request = self.make_request(
			status="In Transit",
			awb="AWB-OLD-1",
			order_ref="SR-ORDER-1",
			shipment_ref="SR-SHIP-1",
			carrier="Delhivery",
			parcels=[{"length": 10, "width": 20, "height": 5, "weight": 1.5, "count": 1}],
		)
		for index, status in enumerate(("Picked Up", "In Transit")):
			frappe.get_doc(
				{
					"doctype": "Shipping Tracking Event",
					"parent": request,
					"parenttype": "Shipping Request",
					"parentfield": "tracking_events",
					"idx": index + 1,
					"status": status,
					"event_id": f"event-{index}",
				}
			).db_insert()
		integration_request = frappe.get_doc(
			{
				"doctype": "Integration Request",
				"integration_request_service": "Shiprocket",
				"reference_doctype": "Shipping Request",
				"reference_docname": request,
			}
		)
		integration_request.db_insert()
		return request, integration_request.name

	def get_shipment(self, request: str):
		return frappe.get_doc("Shipment", {"description_of_content": request})

	def test_a_booked_request_becomes_a_booked_shipment(self):
		request, integration_request = self.make_booked_request()

		execute()

		shipment = self.get_shipment(request)
		self.assertEqual((shipment.docstatus, shipment.status), (1, "Booked"))
		self.assertEqual(
			(shipment.awb_number, shipment.custom_order_ref, shipment.custom_shipment_status),
			("AWB-OLD-1", "SR-ORDER-1", "In Transit"),
		)
		self.assertEqual(
			(shipment.custom_sales_order, shipment.delivery_customer, shipment.custom_shipping_provider),
			(self.sales_order.name, self.sales_order.customer, self.provider),
		)
		self.assertEqual(shipment.delivery_address_name, self.delivery_address)
		self.assertEqual(
			[
				(parcel.length, parcel.width, parcel.height, parcel.weight)
				for parcel in shipment.shipment_parcel
			],
			[(10, 20, 5, 1.5)],
		)
		self.assertEqual(
			[event.status for event in shipment.custom_tracking_events], ["Picked Up", "In Transit"]
		)
		self.assertEqual(
			frappe.db.get_value(
				"Integration Request", integration_request, ["reference_doctype", "reference_docname"]
			),
			("Shipment", shipment.name),
		)

	def test_a_cancelled_request_becomes_a_cancelled_shipment(self):
		request = self.make_request(status="Cancelled", awb="AWB-OLD-2")

		execute()

		shipment = self.get_shipment(request)
		self.assertEqual((shipment.docstatus, shipment.status), (2, "Cancelled"))

	def test_an_unbooked_request_becomes_a_draft_shipment(self):
		request = self.make_request(status="Draft")

		execute()

		shipment = self.get_shipment(request)
		self.assertEqual((shipment.docstatus, shipment.status), (0, "Draft"))

	def test_a_request_without_an_origin_ships_from_the_order_company_address(self):
		request = self.make_request(status="Draft")

		execute()

		self.assertEqual(self.get_shipment(request).pickup_address_name, self.company_address)

	def test_the_old_doctypes_are_dropped(self):
		self.make_request(status="Draft")

		execute()

		self.assertEqual(
			[call.args[:2] for call in self.delete_doc.call_args_list],
			[("DocType", doctype) for doctype in OLD_DOCTYPES],
		)
		self.assertEqual(
			[call.args[0] for call in self.sql_ddl.call_args_list],
			[f"drop table if exists `tab{doctype}`" for doctype in OLD_DOCTYPES],
		)
