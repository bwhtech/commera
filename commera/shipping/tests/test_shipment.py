import frappe
from frappe.tests import IntegrationTestCase

from commera.sdk import STORE_ORDER_TYPE
from commera.shipping.fulfilment import create_shipment
from commera.shipping.providers import use_providers
from commera.shipping.testing import InMemoryShippingProvider
from commera.shipping.tests.test_carrier_import import create_test_address, create_test_provider_profile
from commera.tests.test_admin_orders import make_test_sales_order
from commera.tests.test_order_status import deliver

SERVICE_CODE = "express"


class TestShipmentBooking(IntegrationTestCase):
	"""A Shipment from a Delivery Note, booked with the in-memory carrier."""

	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.profile = create_test_provider_profile()
		self.carrier = InMemoryShippingProvider()
		self.enterContext(use_providers({self.profile: self.carrier}))

		sales_order = make_test_sales_order(order_type=STORE_ORDER_TYPE)
		sales_order.db_set(
			{
				"shipping_address_name": create_test_address("India", "Customer", sales_order.customer),
				"company_address": create_test_address("India", "Company", sales_order.company),
				"custom_shipping_provider": self.profile,
				"custom_shipping_service_code": SERVICE_CODE,
			}
		)
		self.sales_order = sales_order.name
		self.delivery_note = deliver(sales_order).name

	def book(self):
		shipment = frappe.get_doc("Shipment", create_shipment(self.delivery_note))
		shipment.book()
		return shipment

	def test_a_shipment_is_drafted_with_the_customers_choice(self):
		shipment = frappe.get_doc("Shipment", create_shipment(self.delivery_note))

		self.assertEqual(
			(shipment.docstatus, shipment.custom_sales_order, shipment.custom_shipping_provider),
			(0, self.sales_order, self.profile),
		)
		self.assertEqual(shipment.custom_service_code, SERVICE_CODE)
		self.assertTrue(shipment.shipment_parcel)

	def test_booking_buys_the_label_and_submits_the_shipment(self):
		shipment = self.book()

		shipment.reload()
		self.assertEqual((shipment.docstatus, shipment.status), (1, "Booked"))
		self.assertEqual(
			(shipment.awb_number, shipment.custom_shipment_status), ("AWB-MEM-1", "Ready To Ship")
		)
		self.assertEqual(self.carrier.shipments["MEM-1"]["order_reference"], self.sales_order)

	def test_a_delivery_note_ships_once(self):
		create_shipment(self.delivery_note)

		self.assertRaises(frappe.ValidationError, create_shipment, self.delivery_note)

	def test_cancelling_the_booking_cancels_the_shipment_and_frees_the_delivery_note(self):
		shipment = self.book()

		shipment.cancel_booking()

		shipment.reload()
		self.assertEqual((shipment.docstatus, shipment.custom_shipment_status), (2, "Cancelled"))
		self.assertEqual(self.carrier.cancelled, ["MEM-1"])
		self.assertTrue(create_shipment(self.delivery_note))

	def test_a_delivered_scan_completes_the_erpnext_shipment(self):
		shipment = self.book()
		scan = {"timestamp": "2026-10-01 10:00:00", "status": "Delivered", "message": "Handed over"}
		self.carrier.tracking[shipment.awb_number] = {"status": "Delivered", "events": [scan]}

		shipment.sync_status()

		shipment.reload()
		self.assertEqual(
			(shipment.status, shipment.tracking_status, len(shipment.custom_tracking_events)),
			("Completed", "Delivered", 1),
		)
