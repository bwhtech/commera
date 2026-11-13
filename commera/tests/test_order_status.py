# Copyright (c) 2026, company@bwhstudios.com and Contributors

from unittest.mock import patch

import frappe
from erpnext.controllers.accounts_controller import update_child_qty_rate
from frappe.tests import IntegrationTestCase
from frappe.utils.data import flt

from commera.api.admin.orders import get_order
from commera.api.payments import make_sales_invoice
from commera.sdk import STORE_ORDER_TYPE
from commera.shipping.testing import insert_shipment_record
from commera.tests.test_admin_orders import ITEM_RATE, make_drop_ship_order, make_test_sales_order
from commera.tests.test_order_access import make_website_user
from commera.themes.summer_theme.pages.account.dashboard import (
	get_context as get_account_dashboard_context,
)
from commera.utils import can_return, update_sales_order_ecommerce_status

try:
	from erpnext.selling.doctype.sales_order.mapper import make_delivery_note
	from erpnext.stock.doctype.delivery_note.mapper import make_sales_return
except ImportError:
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_return

return_items = frappe.get_module("commera.api.return").return_items


def make_paid_order():
	sales_order = make_test_sales_order()
	sales_invoice = make_sales_invoice(sales_order.name, ignore_permissions=True)
	sales_invoice.flags.ignore_permissions = True
	sales_invoice.insert()
	sales_invoice.submit()
	return sales_order.reload()


def deliver(sales_order, submit=True, first_line_qty=None):
	delivery_note = make_delivery_note(sales_order.name)
	if first_line_qty is not None:
		delivery_note.items = delivery_note.items[:1]
		delivery_note.items[0].qty = first_line_qty
	delivery_note.flags.ignore_permissions = True
	delivery_note.insert()
	if submit:
		delivery_note.submit()
	return delivery_note


class TestOrderStatus(IntegrationTestCase):
	def make_return(self, delivery_note, qty=None):
		sales_return = make_sales_return(delivery_note.name)
		if qty is not None:
			sales_return.items[0].qty = -qty
		sales_return.flags.ignore_permissions = True
		sales_return.insert()
		sales_return.submit()
		return sales_return

	def book_parcel(self, sales_order, status, delivery_note=None):
		insert_shipment_record(sales_order.name, status, delivery_note)

	def status_of(self, sales_order):
		update_sales_order_ecommerce_status(sales_order.name)
		return frappe.db.get_value("Sales Order", sales_order.name, "custom_ecommerce_status")

	def fired_events(self, sales_order):
		return frappe.get_all(
			"Commera Event", filters={"reference_name": sales_order.name}, pluck="event", order_by="creation"
		)

	def test_a_paid_order_is_received_not_delivered(self):
		sales_order = make_paid_order()
		self.assertEqual(flt(sales_order.per_billed), 100)
		self.assertEqual(self.status_of(sales_order), "Order Received")

	def test_a_draft_delivery_note_means_the_order_is_being_packed(self):
		sales_order = make_paid_order()
		deliver(sales_order, submit=False)
		self.assertEqual(self.status_of(sales_order), "Preparing for Shipment")

	def test_without_a_carrier_a_submitted_delivery_note_is_the_delivery(self):
		sales_order = make_paid_order()
		deliver(sales_order)
		self.assertEqual(self.status_of(sales_order), "Delivered")

	def test_shipping_some_units_of_a_line_is_partially_shipped(self):
		sales_order = make_paid_order()
		deliver(sales_order, first_line_qty=1)
		self.assertEqual(self.status_of(sales_order), "Partially Shipped")

	def test_shipping_one_line_of_two_is_partially_shipped(self):
		sales_order = make_test_sales_order(submit=False)
		sales_order.append(
			"items", {"item_code": sales_order.items[0].item_code, "qty": 1, "rate": ITEM_RATE}
		)
		sales_order.save()
		sales_order.submit()
		deliver(sales_order, first_line_qty=sales_order.items[0].qty)
		self.assertEqual(self.status_of(sales_order), "Partially Shipped")

		deliver(sales_order)
		self.assertEqual(self.status_of(sales_order), "Delivered")

	def test_delivery_events_wait_until_every_unit_has_shipped(self):
		sales_order = make_test_sales_order(order_type=STORE_ORDER_TYPE)
		deliver(sales_order, first_line_qty=1)
		self.assertEqual(self.status_of(sales_order), "Partially Shipped")
		self.assertNotIn("order_fulfilled", self.fired_events(sales_order))
		self.assertNotIn("order_delivered", self.fired_events(sales_order))

		deliver(sales_order)
		self.assertEqual(self.status_of(sales_order), "Delivered")
		delivery_events = [
			event
			for event in self.fired_events(sales_order)
			if event in ("order_fulfilled", "order_delivered")
		]
		self.assertEqual(delivery_events, ["order_fulfilled", "order_delivered"])

	def test_cancelling_the_only_shipment_of_a_partial_order_reopens_it(self):
		sales_order = make_paid_order()
		delivery_note = deliver(sales_order, first_line_qty=1)
		self.assertEqual(self.status_of(sales_order), "Partially Shipped")

		delivery_note.cancel()
		self.assertEqual(self.status_of(sales_order), "Order Received")

	def test_cancelling_the_last_shipment_returns_to_partially_shipped(self):
		sales_order = make_paid_order()
		deliver(sales_order, first_line_qty=1)
		last_delivery_note = deliver(sales_order)
		self.assertEqual(self.status_of(sales_order), "Delivered")

		last_delivery_note.cancel()
		self.assertEqual(self.status_of(sales_order), "Partially Shipped")

	def test_a_partially_shipped_order_passes_validation_on_save(self):
		sales_order = make_paid_order()
		deliver(sales_order, first_line_qty=1)
		self.assertEqual(self.status_of(sales_order), "Partially Shipped")

		frappe.get_doc("Sales Order", sales_order.name).save()

	def test_the_order_screen_shows_a_partial_shipment_without_a_carrier_as_partly_fulfilled(self):
		sales_order = make_paid_order()
		deliver(sales_order, first_line_qty=1)
		self.assertEqual(get_order(sales_order.name)["state"]["key"], "partly_fulfilled")

	def test_a_partially_shipped_order_counts_as_open_for_the_shopper(self):
		shopper = make_website_user()
		sales_order = make_paid_order()
		frappe.db.set_value("Sales Order", sales_order.name, "owner", shopper)
		deliver(sales_order, first_line_qty=1)
		self.assertEqual(self.status_of(sales_order), "Partially Shipped")

		context = frappe._dict()
		with self.set_user(shopper):
			get_account_dashboard_context(context)
		self.assertEqual(context.open_order_count, 1)

	def test_reducing_the_order_to_what_shipped_queues_a_recount_and_delivers_it(self):
		sales_order = make_test_sales_order()
		deliver(sales_order, first_line_qty=1)
		self.assertEqual(self.status_of(sales_order), "Partially Shipped")

		line = sales_order.items[0]
		items = [{"docname": line.name, "item_code": line.item_code, "qty": 1, "rate": line.rate}]
		with patch.object(frappe, "enqueue") as enqueue:
			update_child_qty_rate("Sales Order", frappe.as_json(items), sales_order.name)
		queued_methods = [call.args[0] for call in enqueue.call_args_list if call.args]
		self.assertIn("commera.utils.update_sales_order_ecommerce_status", queued_methods)
		self.assertEqual(self.status_of(sales_order), "Delivered")

	def test_closing_a_part_shipped_order_delivers_it_and_reopening_undoes_that(self):
		sales_order = make_test_sales_order(order_type=STORE_ORDER_TYPE)
		deliver(sales_order, first_line_qty=1)
		self.assertEqual(self.status_of(sales_order), "Partially Shipped")

		with patch.object(frappe, "enqueue") as enqueue:
			frappe.get_doc("Sales Order", sales_order.name).update_status("Closed")
		queued_methods = [call.args[0] for call in enqueue.call_args_list if call.args]
		self.assertIn("commera.utils.update_sales_order_ecommerce_status", queued_methods)
		self.assertEqual(self.status_of(sales_order), "Delivered")
		self.assertIn("order_delivered", self.fired_events(sales_order))

		with patch.object(frappe, "enqueue") as enqueue:
			frappe.get_doc("Sales Order", sales_order.name).update_status("Draft")
		queued_methods = [call.args[0] for call in enqueue.call_args_list if call.args]
		self.assertIn("commera.utils.update_sales_order_ecommerce_status", queued_methods)
		self.assertEqual(self.status_of(sales_order), "Partially Shipped")

	def test_closing_an_order_that_shipped_nothing_does_not_deliver_it(self):
		sales_order = make_test_sales_order()
		frappe.get_doc("Sales Order", sales_order.name).update_status("Closed")
		self.assertEqual(self.status_of(sales_order), "Order Received")

	def test_closing_a_part_shipped_order_with_a_parcel_moving_does_not_deliver_it(self):
		sales_order = make_test_sales_order(order_type=STORE_ORDER_TYPE)
		delivery_note = deliver(sales_order, first_line_qty=1)
		self.book_parcel(sales_order, "In Transit", delivery_note=delivery_note.name)
		frappe.get_doc("Sales Order", sales_order.name).update_status("Closed")
		self.assertEqual(self.status_of(sales_order), "Shipped")
		self.assertNotIn("order_delivered", self.fired_events(sales_order))

	def test_a_recount_that_changes_nothing_leaves_the_open_form_saveable(self):
		sales_order = make_paid_order()
		self.assertEqual(self.status_of(sales_order), "Order Received")
		frappe.db.set_value(
			"Sales Order", sales_order.name, "modified", "2020-01-01 00:00:00", update_modified=False
		)

		self.assertEqual(self.status_of(sales_order), "Order Received")
		self.assertEqual(
			str(frappe.db.get_value("Sales Order", sales_order.name, "modified")), "2020-01-01 00:00:00"
		)

	def test_a_parcel_for_part_of_an_order_cannot_outrun_the_unshipped_units(self):
		for carrier_status, expected in (
			("Ready To Ship", "Preparing for Shipment"),
			("In Transit", "Partially Shipped"),
			("Delivered", "Partially Shipped"),
			("RTO", "Returned"),
		):
			with self.subTest(carrier_status=carrier_status):
				sales_order = make_paid_order()
				delivery_note = deliver(sales_order, first_line_qty=1)
				self.book_parcel(sales_order, carrier_status, delivery_note=delivery_note.name)
				self.assertEqual(self.status_of(sales_order), expected)

	def test_a_delivered_parcel_for_part_of_an_order_fires_no_delivery_events(self):
		sales_order = make_test_sales_order(order_type=STORE_ORDER_TYPE)
		delivery_note = deliver(sales_order, first_line_qty=1)
		self.book_parcel(sales_order, "Delivered", delivery_note=delivery_note.name)
		self.assertEqual(self.status_of(sales_order), "Partially Shipped")
		self.assertNotIn("order_fulfilled", self.fired_events(sales_order))
		self.assertNotIn("order_delivered", self.fired_events(sales_order))

	def test_a_booked_parcel_holds_the_order_until_the_carrier_moves_it(self):
		sales_order = make_paid_order()
		deliver(sales_order)
		self.book_parcel(sales_order, "Ready To Ship")
		self.assertEqual(self.status_of(sales_order), "Preparing for Shipment")

	def test_the_carrier_status_sets_the_rung(self):
		for carrier_status, expected in (
			("In Transit", "Shipped"),
			("Out For Delivery", "Shipped"),
			("Delivered", "Delivered"),
			("RTO", "Returned"),
		):
			with self.subTest(carrier_status=carrier_status):
				sales_order = make_paid_order()
				deliver(sales_order)
				self.book_parcel(sales_order, carrier_status)
				self.assertEqual(self.status_of(sales_order), expected)

	def test_a_cancelled_booking_falls_back_to_the_delivery_note(self):
		sales_order = make_paid_order()
		deliver(sales_order)
		self.book_parcel(sales_order, "Cancelled")
		self.assertEqual(self.status_of(sales_order), "Delivered")

	def test_returning_part_of_an_order_is_a_partial_return(self):
		sales_order = make_paid_order()
		delivery_note = deliver(sales_order)
		self.make_return(delivery_note, qty=1)
		self.assertEqual(self.status_of(sales_order), "Partially Returned")

	def test_returning_everything_is_a_return(self):
		sales_order = make_paid_order()
		delivery_note = deliver(sales_order)
		self.make_return(delivery_note)
		self.assertEqual(flt(frappe.db.get_value("Sales Order", sales_order.name, "per_delivered")), 0)
		self.assertEqual(self.status_of(sales_order), "Returned")

	def test_a_cancelled_order_is_cancelled(self):
		sales_order = make_test_sales_order()
		sales_order.cancel()
		self.assertEqual(self.status_of(sales_order), "Cancelled")


class TestMixedOrderStatus(IntegrationTestCase):
	"""A store line ships on a Delivery Note; a drop-ship line ships through its supplier's parcel."""

	book_parcel = TestOrderStatus.book_parcel
	status_of = TestOrderStatus.status_of
	fired_events = TestOrderStatus.fired_events

	def make_mixed_order(self, store_line_qty=1):
		sales_order = make_drop_ship_order(with_store_line=True, store_line_qty=store_line_qty)
		frappe.db.set_value("Sales Order", sales_order.name, "order_type", STORE_ORDER_TYPE)
		return sales_order

	def mark_supplier_lines_received(self, sales_order):
		for line in sales_order.items:
			if line.delivered_by_supplier:
				frappe.db.set_value("Sales Order Item", line.name, "delivered_qty", line.qty)

	def test_delivering_the_store_line_leaves_the_order_in_preparation(self):
		sales_order = self.make_mixed_order()
		deliver(sales_order)
		self.assertEqual(self.status_of(sales_order), "Preparing for Shipment")
		self.assertEqual(self.fired_events(sales_order), [])

	def test_a_part_shipped_store_line_holds_the_order_back_whatever_the_supplier_does(self):
		sales_order = self.make_mixed_order(store_line_qty=2)
		deliver(sales_order, first_line_qty=1)
		self.assertEqual(self.status_of(sales_order), "Preparing for Shipment")

		self.book_parcel(sales_order, "In Transit")
		self.assertEqual(self.status_of(sales_order), "Partially Shipped")

		self.mark_supplier_lines_received(sales_order)
		self.assertEqual(self.status_of(sales_order), "Partially Shipped")
		self.assertEqual(self.fired_events(sales_order), [])

	def test_closing_with_a_short_store_line_waits_for_the_supplier_parcel(self):
		sales_order = self.make_mixed_order(store_line_qty=2)
		deliver(sales_order, first_line_qty=1)
		self.book_parcel(sales_order, "In Transit")
		frappe.get_doc("Sales Order", sales_order.name).update_status("Closed")
		self.assertEqual(self.status_of(sales_order), "Shipped")
		self.assertEqual(self.fired_events(sales_order), ["order_fulfilled"])

	def test_the_supplier_parcel_moving_alone_does_not_ship_the_order(self):
		sales_order = self.make_mixed_order()
		self.book_parcel(sales_order, "In Transit")
		self.assertEqual(self.status_of(sales_order), "Preparing for Shipment")

	def test_the_order_ships_when_every_line_has_left_and_delivers_when_every_line_arrives(self):
		sales_order = self.make_mixed_order()
		deliver(sales_order)
		self.book_parcel(sales_order, "In Transit")
		self.assertEqual(self.status_of(sales_order), "Shipped")
		self.assertEqual(self.fired_events(sales_order), ["order_fulfilled"])

		self.book_parcel(sales_order, "Delivered")
		self.assertEqual(self.status_of(sales_order), "Delivered")
		self.assertEqual(self.status_of(sales_order), "Delivered")
		self.assertEqual(self.fired_events(sales_order), ["order_fulfilled", "order_delivered"])

	def test_the_store_carrier_parcel_is_not_read_as_the_supplier_parcel(self):
		sales_order = self.make_mixed_order()
		delivery_note = deliver(sales_order)
		self.book_parcel(sales_order, "Delivered", delivery_note=delivery_note.name)
		self.assertEqual(self.status_of(sales_order), "Preparing for Shipment")

	def test_the_supplier_receipt_on_the_purchase_order_delivers_the_drop_ship_line(self):
		sales_order = self.make_mixed_order()
		deliver(sales_order)
		self.mark_supplier_lines_received(sales_order)
		self.assertEqual(self.status_of(sales_order), "Delivered")
		self.assertEqual(self.fired_events(sales_order), ["order_fulfilled", "order_delivered"])

	def test_a_drop_ship_only_order_follows_its_supplier_parcel(self):
		sales_order = make_drop_ship_order()
		self.assertEqual(self.status_of(sales_order), "Order Received")
		self.book_parcel(sales_order, "In Transit")
		self.assertEqual(self.status_of(sales_order), "Shipped")
		self.book_parcel(sales_order, "Delivered")
		self.assertEqual(self.status_of(sales_order), "Delivered")


class TestReturnWindow(IntegrationTestCase):
	def test_a_paid_undelivered_order_cannot_be_returned(self):
		self.assertFalse(can_return(make_paid_order().name, 30))

	def test_the_window_opens_at_delivery(self):
		sales_order = make_paid_order()
		delivery_note = deliver(sales_order, submit=False)
		self.assertFalse(can_return(sales_order.name, 30))

		delivery_note.submit()
		self.assertTrue(can_return(sales_order.name, 30))
		self.assertFalse(can_return(sales_order.name, 0))


class TestReturnItems(IntegrationTestCase):
	def setUp(self):
		frappe.db.set_single_value("Commera Settings", "return_period", 30)

	def request_return(self, sales_order):
		return_items(sales_order.name, [{"item_code": sales_order.items[0].item_code, "reason": "Too big"}])

	def test_an_undelivered_order_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.request_return(make_paid_order())

	def test_a_delivered_order_drafts_a_return_note(self):
		sales_order = make_paid_order()
		deliver(sales_order)
		self.request_return(sales_order)
		self.assertTrue(
			frappe.db.exists(
				"Delivery Note Item",
				{"against_sales_order": sales_order.name, "docstatus": 0, "qty": ["<", 0]},
			)
		)

	def test_the_same_item_cannot_be_returned_twice(self):
		sales_order = make_paid_order()
		deliver(sales_order)
		self.request_return(sales_order)
		with self.assertRaises(frappe.ValidationError):
			self.request_return(sales_order)

	def test_a_delivered_order_is_returned_once(self):
		self.addCleanup(frappe.set_user, "Administrator")
		shopper = make_website_user()
		sales_order = make_paid_order()
		sales_order.db_set("owner", shopper)
		deliver(sales_order)
		frappe.set_user(shopper)

		self.request_return(sales_order)

		self.assertTrue(
			frappe.db.exists(
				"Delivery Note Item",
				{"against_sales_order": sales_order.name, "docstatus": 0, "qty": ["<", 0]},
			)
		)
		with self.assertRaisesRegex(frappe.ValidationError, "already been returned"):
			self.request_return(sales_order)

	def test_a_shopper_cannot_return_another_shoppers_order(self):
		self.addCleanup(frappe.set_user, "Administrator")
		sales_order = make_paid_order()
		sales_order.db_set("owner", make_website_user())
		deliver(sales_order)
		frappe.set_user(make_website_user())

		with self.assertRaises(frappe.PermissionError):
			self.request_return(sales_order)

		self.assertFalse(
			frappe.db.exists("Delivery Note Item", {"against_sales_order": sales_order.name, "qty": ["<", 0]})
		)
