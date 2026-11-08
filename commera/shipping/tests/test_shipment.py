from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.sdk import STORE_ORDER_TYPE
from commera.shipping.fulfilment import create_shipment
from commera.shipping.providers import use_providers
from commera.shipping.shipment import book, cancel_booking, schedule_pickup, sync_status
from commera.shipping.testing import InMemoryShippingProvider
from commera.shipping.tests.test_carrier_import import create_test_address, create_test_provider_profile
from commera.tests.test_admin_orders import make_test_sales_order
from commera.tests.test_order_status import deliver

SERVICE_CODE = "express"


class TestShipmentBooking(IntegrationTestCase):
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
		shipment = create_shipment(self.delivery_note)
		book(shipment)
		return frappe.get_doc("Shipment", shipment)

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

	def test_a_carrier_rate_without_a_shipping_service_still_ships(self):
		frappe.db.set_value("Sales Order", self.sales_order, "custom_delivery_option", "Carrier Surface")

		shipment = frappe.get_doc("Shipment", create_shipment(self.delivery_note))

		self.assertEqual(
			(shipment.custom_service_code, shipment.custom_shipping_service), (SERVICE_CODE, None)
		)

	def test_booking_holds_its_lock_until_the_carrier_answers(self):
		shipment = frappe.get_doc("Shipment", create_shipment(self.delivery_note))

		with patch.object(frappe.db, "commit", side_effect=AssertionError("committed mid-booking")):
			book(shipment.name)

		shipment.reload()
		self.assertEqual(shipment.docstatus, 1)

	def test_a_booked_shipment_cancels_only_with_the_carrier(self):
		shipment = self.book()

		self.assertRaises(frappe.ValidationError, shipment.cancel)
		self.assertEqual(self.carrier.cancelled, [])

	def test_a_delivery_note_ships_once(self):
		create_shipment(self.delivery_note)

		self.assertRaises(frappe.ValidationError, create_shipment, self.delivery_note)

	def test_cancelling_the_booking_cancels_the_shipment_and_frees_the_delivery_note(self):
		shipment = self.book()

		cancel_booking(shipment.name)

		shipment.reload()
		self.assertEqual((shipment.docstatus, shipment.custom_shipment_status), (2, "Cancelled"))
		self.assertEqual(self.carrier.cancelled, ["MEM-1"])
		self.assertTrue(create_shipment(self.delivery_note))

	def test_a_delivered_scan_completes_the_erpnext_shipment(self):
		shipment = self.book()
		scan = {"timestamp": "2026-10-01 10:00:00", "status": "Delivered", "message": "Handed over"}
		self.carrier.tracking[shipment.awb_number] = {"status": "Delivered", "events": [scan]}

		sync_status(shipment.name)

		shipment.reload()
		self.assertEqual(
			(shipment.status, shipment.tracking_status, len(shipment.custom_tracking_events)),
			("Completed", "Delivered", 1),
		)

	def sync_to(self, shipment, status: str) -> str:
		self.carrier.tracking[shipment.awb_number] = {"status": status, "events": []}
		return sync_status(shipment.name)

	def test_a_carrier_reattempt_after_a_failed_delivery_moves_the_shipment_on(self):
		shipment = self.book()

		self.assertEqual(
			[
				self.sync_to(shipment, status)
				for status in ("Out For Delivery", "Undelivered", "Out For Delivery")
			],
			["Out For Delivery", "Undelivered", "Out For Delivery"],
		)
		self.assertEqual(self.sync_to(shipment, "Delivered"), "Delivered")

	def test_a_parcel_on_its_way_back_to_the_store_never_becomes_delivered(self):
		shipment = self.book()
		self.sync_to(shipment, "RTO")

		self.assertEqual(self.sync_to(shipment, "Delivered"), "RTO")
		self.assertEqual(self.sync_to(shipment, "Lost"), "Lost")

	def test_a_cancelled_partial_booking_is_not_finished_at_the_carrier(self):
		shipment = frappe.get_doc("Shipment", create_shipment(self.delivery_note))
		shipment.submit()
		shipment.db_set("custom_order_ref", "MEM-PARTIAL")
		cancel_booking(shipment.name)

		self.assertRaisesRegex(frappe.ValidationError, "cannot be booked", book, shipment.name)
		self.assertEqual(self.carrier.shipments, {})

	def test_a_pickup_is_only_scheduled_before_the_carrier_collects(self):
		shipment = self.book()
		schedule_pickup(shipment.name)
		shipment.reload()
		self.assertEqual(shipment.custom_shipment_status, "Pickup Scheduled")

		self.sync_to(shipment, "Delivered")

		self.assertRaisesRegex(
			frappe.ValidationError, "no longer be scheduled", schedule_pickup, shipment.name
		)
		self.assertEqual(self.carrier.pickups, ["MEM-1"])
