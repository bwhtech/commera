# Copyright (c) 2026, company@bwhstudios.com and Contributors

from unittest.mock import patch

import frappe
from bwh_payments.bwh_payments import webhook
from bwh_payments.bwh_payments.doctype.razorpay_gateway_settings import razorpay_gateway_settings
from bwh_payments.bwh_payments.doctype.razorpay_gateway_settings.test_razorpay_gateway_settings import (
	RAZORPAY_GATEWAY,
	RAZORPAY_WEBHOOK_SECRET,
	configure_razorpay_gateway,
)
from bwh_payments.currency import to_minor_units
from bwh_payments.tests.fake_razorpay import (
	FakeRazorpay,
	build_payment_link_paid_event,
	sign_razorpay_payload,
)
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, getdate, now_datetime
from frappe.utils.data import flt
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.payments import confirm_payment, open_checkout, validate_cart_is_not_in_checkout
from commera.api.shipping import get_charge_amount
from commera.jobs import sync_pending_gateway_payments
from commera.tests import test_payment_hooks
from commera.tests.test_payment_hooks import COMPANY, DEFAULT_CASH_ACCOUNT


class TestRazorpayCheckout(IntegrationTestCase):
	"""The storefront's Razorpay journey, checkout to refund. Only the "gateway driver" helpers know how the
	transport is faked: a bwh_payments refactor may change their bodies, never the tests."""

	# The storefront fixtures the Stripe suite already builds; only the gateway differs here. Reached through
	# the module and dropped after: a TestCase at module scope would be collected and run a second time.
	StripeSuite = test_payment_hooks.TestPaymentHookIdempotency
	ensure_fiscal_year = StripeSuite.ensure_fiscal_year
	ensure_price_list = StripeSuite.ensure_price_list
	create_item = StripeSuite.create_item
	create_customer = StripeSuite.create_customer
	create_contact = StripeSuite.create_contact
	create_cart_quotation = StripeSuite.create_cart_quotation
	create_shopper_user = StripeSuite.create_shopper_user
	submitted_sales_orders = StripeSuite.submitted_sales_orders
	submitted_sales_invoices = StripeSuite.submitted_sales_invoices
	submitted_payment_entries = StripeSuite.submitted_payment_entries
	create_refund_payment_entry = StripeSuite.create_refund_payment_entry
	del StripeSuite

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Every Razorpay call writes an Integration Request through create_request_log, which commits. The
		# test case only rolls back at class end, so without this the whole journey would land on the site.
		commit_patch = patch.object(frappe.db, "commit")
		commit_patch.start()
		cls.addClassCleanup(cls.discard_class_writes, commit_patch)

		configure_razorpay_gateway()
		cls.ensure_mode_of_payment()
		cls.ensure_price_list()
		cls.ensure_fiscal_year()

	@classmethod
	def discard_class_writes(cls, commit_patch):
		frappe.db.rollback()
		commit_patch.stop()
		# Also empties the per-worker payment modes cache, or the next class would see Razorpay offered.
		frappe.clear_cache()

	@classmethod
	def ensure_mode_of_payment(cls):
		"""place_order posts the Payment Entry under a Mode of Payment named exactly like the gateway."""
		if not frappe.db.exists("Mode of Payment", RAZORPAY_GATEWAY):
			frappe.get_doc(
				{
					"doctype": "Mode of Payment",
					"mode_of_payment": RAZORPAY_GATEWAY,
					"type": "Bank",
					"enabled": 1,
				}
			).insert(ignore_permissions=True)

		mode_of_payment = frappe.get_doc("Mode of Payment", RAZORPAY_GATEWAY)
		if not any(row.company == COMPANY for row in mode_of_payment.accounts):
			mode_of_payment.append("accounts", {"company": COMPANY, "default_account": DEFAULT_CASH_ACCOUNT})
			mode_of_payment.save(ignore_permissions=True)

	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.set_user, "Administrator")
		self.patch_razorpay_transport()

		self.item_code = self.create_item()
		self.customer = self.create_customer()
		self.contact_email = self.create_contact(self.customer)
		self.quotation = self.create_cart_quotation()
		self.shopper = self.create_shopper_user(self.contact_email)

	# -- gateway driver -----------------------------------------------------------------------------
	# Recordings come back in Razorpay's own request shapes; a stub must keep producing the same ones.

	def patch_razorpay_transport(self):
		FakeRazorpay.reset()
		for name, fake in (("make_post_request", FakeRazorpay.post), ("make_get_request", FakeRazorpay.get)):
			transport_patch = patch.object(razorpay_gateway_settings, name, fake)
			transport_patch.start()
			self.addCleanup(transport_patch.stop)

	def created_links(self) -> list[dict]:
		return FakeRazorpay.created_links

	def checkout_url(self, link_id: str) -> str:
		return FakeRazorpay.links[link_id]["short_url"]

	def link_status(self, link_id: str) -> str:
		return FakeRazorpay.links[link_id]["status"]

	def shopper_pays(self, link_id: str) -> str:
		"""The shopper completes the hosted page: Razorpay captures a payment and closes the link."""
		FakeRazorpay.links[link_id]["status"] = "paid"
		return FakeRazorpay.add_payment(link_id, "captured")

	def refunds_sent(self) -> list[dict]:
		return FakeRazorpay.created_refunds

	def deliver_paid_webhook(self, link_id: str) -> dict:
		payload = build_payment_link_paid_event(link_id)
		builder = EnvironBuilder(
			method="POST", path="/api/method/bwh_payments.bwh_payments.webhook.handle", data=payload
		)
		builder.headers.extend(
			{
				"Content-Type": "application/json",
				"X-Razorpay-Event-Id": f"evt_{link_id}",
				"X-Razorpay-Signature": sign_razorpay_payload(payload, RAZORPAY_WEBHOOK_SECRET),
			}
		)
		environ = builder.get_environ()
		environ["QUERY_STRING"] = f"gateway={RAZORPAY_GATEWAY}"

		for attr in ("request", "request_ip", "response"):
			self.addCleanup(setattr, frappe.local, attr, getattr(frappe.local, attr, None))
		frappe.local.request = Request(environ)
		# Set by the WSGI handler in production; the webhook's rate limiter keys on it.
		frappe.local.request_ip = "127.0.0.1"
		frappe.local.response = frappe._dict()
		return webhook.handle()

	# -- journey helpers ----------------------------------------------------------------------------

	def open_razorpay_checkout(self):
		# Lower case on purpose: the storefront sends whatever the shopper's radio button carried.
		checkout = open_checkout(self.quotation, "razorpay")
		return frappe.get_doc("Gateway Payment Request", {"order_url": checkout["order_url"]})

	# -- tests --------------------------------------------------------------------------------------

	def test_checkout_opens_a_razorpay_payment_link_for_the_cart_total(self):
		payment_request = self.open_razorpay_checkout()

		self.assertEqual(payment_request.gateway, RAZORPAY_GATEWAY)
		self.assertEqual(payment_request.status, "Pending")
		self.assertEqual(payment_request.ref_doctype, "Quotation")
		self.assertEqual(payment_request.ref_docname, self.quotation.name)
		self.quotation.reload()
		self.assertEqual(flt(payment_request.amount), get_charge_amount(self.quotation))

		[link] = self.created_links()
		self.assertEqual(
			link["amount"], to_minor_units(payment_request.amount, payment_request.currency_code)
		)
		self.assertEqual(link["currency"], payment_request.currency_code.upper())
		self.assertEqual(link["reference_id"], payment_request.name)
		self.assertIn(f"reference_id={payment_request.name}", link["callback_url"])
		self.assertEqual(link["customer"]["email"], self.contact_email)
		self.assertEqual(payment_request.order_url, self.checkout_url(payment_request.order_ref))

	def test_a_paid_webhook_places_the_order_and_books_the_payment(self):
		payment_request = self.open_razorpay_checkout()
		self.shopper_pays(payment_request.order_ref)

		response = self.deliver_paid_webhook(payment_request.order_ref)

		self.assertEqual(response, {"status": "ok"})
		payment_request.reload()
		self.assertEqual(payment_request.status, "Paid")

		sales_orders = self.submitted_sales_orders()
		self.assertEqual(len(sales_orders), 1)
		self.assertEqual(payment_request.ref_doctype, "Sales Order")
		self.assertEqual(payment_request.ref_docname, sales_orders[0])

		sales_invoices = self.submitted_sales_invoices(sales_orders[0])
		self.assertEqual(len(sales_invoices), 1)
		payment_entries = self.submitted_payment_entries(sales_invoices[0])
		self.assertEqual(len(payment_entries), 1)
		payment_entry = frappe.db.get_value(
			"Payment Entry",
			payment_entries[0],
			["reference_no", "mode_of_payment", "paid_amount"],
			as_dict=True,
		)
		self.assertEqual(payment_entry.reference_no, payment_request.order_ref)
		self.assertEqual(payment_entry.mode_of_payment, RAZORPAY_GATEWAY)
		self.assertEqual(flt(payment_entry.paid_amount), flt(payment_request.amount))

	def test_a_replayed_webhook_does_not_place_a_second_order(self):
		payment_request = self.open_razorpay_checkout()
		self.shopper_pays(payment_request.order_ref)

		self.deliver_paid_webhook(payment_request.order_ref)
		self.deliver_paid_webhook(payment_request.order_ref)

		self.assertEqual(len(self.submitted_sales_orders()), 1)
		self.assertEqual(frappe.db.count("Sales Order", {"customer": self.customer}), 1)

	def test_the_return_page_confirms_a_paid_link_without_a_webhook(self):
		payment_request = self.open_razorpay_checkout()
		self.shopper_pays(payment_request.order_ref)

		frappe.set_user(self.shopper)
		# Razorpay's callback lands on the confirmation page carrying our reference_id.
		result = confirm_payment(payment_request.name)

		self.assertEqual(result["status"], "Paid")
		sales_orders = self.submitted_sales_orders()
		self.assertEqual(len(sales_orders), 1)
		self.assertEqual(result["order_name"], sales_orders[0])

	def test_the_return_page_leaves_an_unpaid_link_pending(self):
		payment_request = self.open_razorpay_checkout()

		frappe.set_user(self.shopper)
		result = confirm_payment(payment_request.name)

		self.assertEqual(result["status"], "Pending")
		self.assertEqual(self.submitted_sales_orders(), [])

	def test_editing_the_cart_cancels_an_abandoned_payment_link(self):
		payment_request = self.open_razorpay_checkout()

		validate_cart_is_not_in_checkout(self.quotation.name)

		payment_request.reload()
		self.assertEqual(payment_request.status, "Cancelled")
		self.assertEqual(self.link_status(payment_request.order_ref), "cancelled")

	def test_a_paid_link_keeps_the_cart_locked(self):
		payment_request = self.open_razorpay_checkout()
		self.shopper_pays(payment_request.order_ref)

		with self.assertRaises(frappe.ValidationError) as raised:
			validate_cart_is_not_in_checkout(self.quotation.name)

		self.assertIn("already been paid", str(raised.exception))
		self.assertEqual(self.link_status(payment_request.order_ref), "paid")

	def test_the_sweep_places_an_order_the_shopper_never_came_back_for(self):
		payment_request = self.open_razorpay_checkout()
		self.shopper_pays(payment_request.order_ref)
		frappe.db.set_value(
			"Gateway Payment Request",
			payment_request.name,
			"creation",
			add_to_date(now_datetime(), minutes=-30),
			update_modified=False,
		)

		sync_pending_gateway_payments()

		self.assertEqual(
			frappe.db.get_value("Gateway Payment Request", payment_request.name, "status"), "Paid"
		)
		self.assertEqual(len(self.submitted_sales_orders()), 1)

	def test_a_refund_payment_entry_refunds_the_captured_razorpay_payment(self):
		payment_request = self.open_razorpay_checkout()
		payment_id = self.shopper_pays(payment_request.order_ref)
		self.deliver_paid_webhook(payment_request.order_ref)

		self.payment_request = payment_request  # the borrowed helper refunds against self.payment_request
		self.create_refund_payment_entry(50, mode_of_payment=RAZORPAY_GATEWAY)

		self.assertEqual(
			self.refunds_sent(),
			[{"payment_id": payment_id, "amount": to_minor_units(50, payment_request.currency_code)}],
		)
		payment_request.reload()
		self.assertEqual(flt(payment_request.refund_amount), 50.0)
		self.assertEqual(payment_request.status, "Partially Refunded")
		self.assertTrue(payment_request.refund_id.startswith("rfnd_"))
