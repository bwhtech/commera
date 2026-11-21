# Copyright (c) 2026, company@bwhstudios.com and Contributors

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.payment_hooks import on_payment_request_update
from commera.notifications import seed_customer_emails
from commera.plugin_events import NOTIFICATIONS_HANDLER, fire_event, get_event_key
from commera.storefront_access import get_store_name
from commera.tests import test_customer_emails, test_payment_hooks
from commera.tests.test_admin_customers import make_customer, make_item, make_webshop_order
from commera.tests.test_customer_emails import SHOPPER

ORDER_EVENTS = (
	("order_placed", None, {}, "Order {0} confirmed"),
	("order_cancelled", None, {}, "Order {0} is cancelled"),
	(
		"order_shipment_dispatched",
		"SHIP-ZZ-1",
		{"shipment": "SHIP-ZZ-1", "carrier": "Delhivery", "awb": "1490223188765", "tracking_url": None},
		"Your order {0} has shipped",
	),
	("order_delivered", None, {}, "Your order {0} was delivered"),
	(
		"order_refunded",
		"ACC-PAY-ZZ-1",
		{"payment_entry": "ACC-PAY-ZZ-1", "amount": 150.0},
		"Your refund for order {0} is on its way",
	),
	(
		"order_returned",
		"returned",
		{"status": "Returned", "partial": False},
		"We received your return for order {0}",
	),
)


def run_enqueued_jobs_now(test_case):
	enqueue = frappe.enqueue

	def enqueue_now(method, *args, **kwargs):
		kwargs.update(now=True, enqueue_after_commit=False)
		return enqueue(method, *args, **kwargs)

	for enqueue_patch in (
		patch.object(frappe, "enqueue", side_effect=enqueue_now),
		patch.object(frappe.db, "commit"),
		patch.object(frappe.db, "rollback"),
	):
		enqueue_patch.start()
		test_case.addCleanup(enqueue_patch.stop)


class TestOrderEventEmails(IntegrationTestCase):
	get_queued_emails = test_customer_emails.TestCustomerEmails.get_queued_emails
	set_email_row = test_customer_emails.TestCustomerEmails.set_email_row
	clear_settings_cache = test_customer_emails.TestCustomerEmails.clear_settings_cache

	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(self.clear_settings_cache)
		self.addCleanup(setattr, frappe.flags, "mute_emails", frappe.flags.mute_emails)
		frappe.flags.mute_emails = True
		seed_customer_emails()
		self.clear_settings_cache()
		run_enqueued_jobs_now(self)

	def make_order(self, qty=1):
		sales_order = make_webshop_order(make_customer(), make_item(), qty=qty)
		sales_order.db_set("contact_email", SHOPPER)
		return sales_order

	def fire(self, event: str, sales_order, data: dict | None = None, key: str | None = None):
		fire_event(event, "Sales Order", sales_order.name, data=data, key=key)

	def email_delivery_status(self, event: str, sales_order, key: str | None = None) -> list[str]:
		return frappe.get_all(
			"Commera Event Delivery",
			filters={
				"parent": get_event_key(event, "Sales Order", sales_order.name, key),
				"handler": NOTIFICATIONS_HANDLER,
			},
			pluck="status",
		)

	def test_each_order_event_emails_the_shopper_once(self):
		for event, key, data, subject in ORDER_EVENTS:
			with self.subTest(event=event):
				sales_order = self.make_order()

				self.fire(event, sales_order, data, key)
				self.fire(event, sales_order, data, key)

				[email] = self.get_queued_emails(sales_order.name)
				self.assertEqual(email["recipients"], [SHOPPER])
				self.assertEqual(email["subject"], subject.format(sales_order.name))
				self.assertEqual(self.email_delivery_status(event, sales_order, key), ["Done"])

	def test_a_turned_off_email_sends_nothing(self):
		self.set_email_row("order_delivered", enabled=0)
		sales_order = self.make_order()

		self.fire("order_delivered", sales_order)

		self.assertEqual(self.get_queued_emails(sales_order.name), [])
		self.assertEqual(self.email_delivery_status("order_delivered", sales_order), ["Done"])

	def test_a_store_with_no_outgoing_email_account_skips_without_retrying(self):
		frappe.flags.mute_emails = False
		sales_order = self.make_order()

		with patch("commera.notifications.EmailAccount.find_outgoing", return_value=None):
			self.fire("order_delivered", sales_order)

		self.assertEqual(self.get_queued_emails(sales_order.name), [])
		self.assertEqual(self.email_delivery_status("order_delivered", sales_order), ["Done"])

	def test_an_order_without_an_email_address_sends_nothing(self):
		sales_order = make_webshop_order(make_customer(), make_item())

		self.fire("order_delivered", sales_order)

		self.assertEqual(self.get_queued_emails(sales_order.name), [])
		self.assertEqual(self.email_delivery_status("order_delivered", sales_order), ["Done"])

	def test_a_shipment_with_its_items_lists_the_parcel(self):
		sales_order = self.make_order(qty=2)
		item = sales_order.items[0]
		data = {
			"shipment": "SHIP-ZZ-2",
			"carrier": "Delhivery",
			"awb": "1490223188765",
			"tracking_url": "https://track.example.com/1490223188765",
			"line_items": [{"item_code": item.item_code, "item_name": item.item_name, "qty": 1}],
		}

		self.fire("order_shipment_dispatched", sales_order, data, "SHIP-ZZ-2")

		[email] = self.get_queued_emails(sales_order.name)
		self.assertIn("In this parcel", email["html"])
		self.assertIn(item.item_name, email["html"])
		self.assertIn("part of your order is on its way", email["html"].lower())
		self.assertIn("1490223188765", email["html"])
		self.assertIn("https://track.example.com/1490223188765", email["html"])

	def test_a_shipment_without_its_items_lists_none(self):
		sales_order = self.make_order()
		data = {"shipment": "SHIP-ZZ-3", "carrier": "Own fleet", "awb": None, "tracking_url": None}

		self.fire("order_shipment_dispatched", sales_order, data, "SHIP-ZZ-3")

		[email] = self.get_queued_emails(sales_order.name)
		self.assertNotIn("In this parcel", email["html"])
		self.assertIn("your order is on its way", email["html"].lower())
		self.assertNotIn("part of your order", email["html"].lower())

	def test_each_shipment_of_an_order_sends_its_own_email(self):
		sales_order = self.make_order()

		for shipment in ("SHIP-ZZ-4", "SHIP-ZZ-5"):
			self.fire("order_shipment_dispatched", sales_order, {"shipment": shipment}, shipment)

		self.assertEqual(len(self.get_queued_emails(sales_order.name)), 2)


class TestPlacedAndFailedPaymentEmails(IntegrationTestCase):
	create_item = test_payment_hooks.TestPaymentHookIdempotency.create_item
	create_customer = test_payment_hooks.TestPaymentHookIdempotency.create_customer
	create_contact = test_payment_hooks.TestPaymentHookIdempotency.create_contact
	create_cart_quotation = test_payment_hooks.TestPaymentHookIdempotency.create_cart_quotation
	create_shopper_user = test_payment_hooks.TestPaymentHookIdempotency.create_shopper_user
	create_paid_payment_request = test_payment_hooks.TestPaymentHookIdempotency.create_paid_payment_request
	create_pending_payment_request = (
		test_payment_hooks.TestPaymentHookIdempotency.create_pending_payment_request
	)
	place_cod_order_for_cart = test_payment_hooks.TestPaymentHookIdempotency.place_cod_order_for_cart
	submitted_sales_orders = test_payment_hooks.TestPaymentHookIdempotency.submitted_sales_orders
	get_queued_emails = test_customer_emails.TestCustomerEmails.get_queued_emails

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		test_payment_hooks.TestPaymentHookIdempotency.setUpClass()

	@classmethod
	def tearDownClass(cls):
		test_payment_hooks.TestPaymentHookIdempotency.tearDownClass()
		super().tearDownClass()

	def setUp(self):
		self.addCleanup(setattr, frappe.flags, "mute_emails", frappe.flags.mute_emails)
		frappe.flags.mute_emails = True
		test_payment_hooks.TestPaymentHookIdempotency.setUp(self)
		seed_customer_emails()

	def confirmations(self, sales_order: str) -> list[dict]:
		return [
			email
			for email in self.get_queued_emails(sales_order)
			if email["subject"] == f"Order {sales_order} confirmed"
		]

	def test_a_cod_order_is_confirmed_once(self):
		run_enqueued_jobs_now(self)

		sales_order = self.place_cod_order_for_cart()

		[email] = self.confirmations(sales_order.name)
		self.assertEqual(email["recipients"], [self.contact_email])

	def test_a_prepaid_order_is_confirmed_once(self):
		run_enqueued_jobs_now(self)

		on_payment_request_update(self.payment_request)
		on_payment_request_update(self.payment_request.reload())

		[sales_order] = self.submitted_sales_orders()
		[email] = self.confirmations(sales_order)
		self.assertEqual(email["recipients"], [self.contact_email])

	def test_a_failed_payment_emails_the_shopper_once_per_request(self):
		quotation = self.create_cart_quotation()
		requests = [self.create_pending_payment_request(quotation) for attempt in range(2)]

		for payment_request in requests:
			payment_request.status = "Not Paid"
			payment_request.save(ignore_permissions=True)
			payment_request.reload().save(ignore_permissions=True)

		emails = self.get_queued_emails(quotation.name)
		self.assertEqual(len(emails), 2)
		for email in emails:
			self.assertEqual(email["recipients"], [self.contact_email])
			self.assertEqual(email["subject"], f"Your payment to {get_store_name()} didn't go through")
			self.assertIn("/cart", email["html"])

	def test_a_cancelled_payment_sends_nothing(self):
		quotation = self.create_cart_quotation()
		payment_request = self.create_pending_payment_request(quotation)

		payment_request.status = "Cancelled"
		payment_request.save(ignore_permissions=True)

		self.assertEqual(self.get_queued_emails(quotation.name), [])
