# Copyright (c) 2026, company@bwhstudios.com and Contributors

import frappe
from bwh_payments_core import testing
from bwh_payments_core.connectors.razorpay.stub import StubRazorpayClient
from bwh_payments_core.connectors.stripe.stub import StubStripeClient
from bwh_payments_core.engine.payment_request import refund_on_payment_entry
from frappe.tests import IntegrationTestCase
from frappe.utils.data import flt

from commera.payment_gateways import api
from commera.payment_gateways.doctype.gateway_payment_request.gateway_payment_request import RETURN_ENDPOINT

GATEWAY = "Stripe Test Gateway"
WEBHOOK_SECRET = "whsec_test_secret"
IGNORE_TEST_RECORD_DEPENDENCIES = ["Address", "Company", "Customer", "Payment Request"]


def configure_stripe_gateway():
	settings = frappe.get_single("Stripe Gateway Settings")
	settings.update(
		{
			"enabled": 1,
			"mode": "Test",
			"public_key": "pk_test_x",
			"private_key": "sk_test_x",
			"webhook_secret": WEBHOOK_SECRET,
			"success_url": "https://shop.test/en/account/orders/confirmation",
			"failure_url": "https://shop.test/en/cart/checkout",
		}
	)
	settings.save(ignore_permissions=True)

	if not frappe.db.exists("Payment Gateway Profile", GATEWAY):
		frappe.get_doc(
			{
				"doctype": "Payment Gateway Profile",
				"name": GATEWAY,
				"gateway_settings": "Stripe Gateway Settings",
				"enabled": 1,
			}
		).insert(ignore_permissions=True)


def remove_stripe_gateway():
	requests = frappe.get_all("Gateway Payment Request", filters={"gateway": GATEWAY}, pluck="name")
	if requests:
		frappe.db.delete("Gateway Refund", {"payment_request": ["in", requests]})
		frappe.db.delete("Gateway Payment Request", {"name": ["in", requests]})
	frappe.db.delete("Integration Request", {"integration_request_service": ["like", f"{GATEWAY} %"]})
	frappe.delete_doc(
		"Payment Gateway Profile", GATEWAY, ignore_missing=True, ignore_permissions=True, force=True
	)
	frappe.db.set_single_value(
		"Stripe Gateway Settings",
		{"enabled": 0, "public_key": "", "private_key": "", "webhook_secret": ""},
	)


class TestGatewayPaymentRequest(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.reference = frappe.get_doc({"doctype": "ToDo", "description": "payment engine test"}).insert()
		cls.gateway = testing.configure_test_gateway()
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback()
		testing.remove_test_gateway()
		frappe.delete_doc("ToDo", cls.reference.name, force=True)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		testing.reset()
		StubStripeClient.reset()

	def make_request(self, amount: float = 1000, **values):
		return frappe.get_doc(
			{
				"doctype": "Gateway Payment Request",
				"gateway": self.gateway,
				"amount": amount,
				"currency_code": "INR",
				"ref_doctype": "ToDo",
				"ref_docname": self.reference.name,
				**values,
			}
		).insert(ignore_permissions=True)

	def make_paid_request(self, amount: float = 1000):
		payment_request = self.make_request(amount)
		testing.pay(payment_request.name)
		payment_request.reload()
		return payment_request

	def get_refunds(self, payment_request) -> list:
		return frappe.get_all(
			"Gateway Refund",
			filters={"payment_request": payment_request.name},
			fields=["amount", "status", "refund_id", "payment_entry"],
			order_by="creation asc",
		)

	def test_inserting_a_request_opens_a_gateway_session(self):
		payment_request = self.make_request()

		self.assertEqual(payment_request.status, "Pending")
		self.assertTrue(payment_request.order_ref)
		self.assertTrue(payment_request.order_url)

	def test_paying_settles_the_request_once(self):
		payment_request = self.make_paid_request()
		self.assertEqual(payment_request.status, "Paid")
		self.assertTrue(payment_request.gateway_transaction_ref)

		modified = payment_request.modified
		payment_request.sync_status()
		payment_request.reload()
		self.assertEqual(payment_request.status, "Paid")
		self.assertEqual(payment_request.modified, modified, "a settled request never asks the gateway again")

	def test_a_partial_then_full_refund_fills_the_ledger(self):
		payment_request = self.make_paid_request(1000)

		with testing.without_commits():
			payment_request.refund(400)
			payment_request.reload()
			self.assertEqual(payment_request.status, "Partially Refunded")
			self.assertEqual(flt(payment_request.refund_amount), 400)

			payment_request.refund()
			payment_request.reload()

		self.assertEqual(payment_request.status, "Refunded")
		self.assertEqual(flt(payment_request.refund_amount), 1000)
		self.assertEqual(
			[(flt(row.amount), row.status) for row in self.get_refunds(payment_request)],
			[(400, "Processed"), (600, "Processed")],
		)

	def test_a_refund_cannot_exceed_what_is_left(self):
		payment_request = self.make_paid_request(1000)

		with testing.without_commits():
			payment_request.refund(700)
			payment_request.reload()
			with self.assertRaises(frappe.ValidationError):
				payment_request.refund(400)

		self.assertEqual(len(self.get_refunds(payment_request)), 1)

	def test_a_refused_refund_is_recorded_as_failed(self):
		payment_request = self.make_paid_request(1000)
		testing.set_next_refund_status("Failed")

		with testing.without_commits():
			with self.assertRaises(frappe.ValidationError):
				payment_request.refund(100)
			payment_request.reload()

		self.assertEqual([row.status for row in self.get_refunds(payment_request)], ["Failed"])
		self.assertEqual(flt(payment_request.refund_amount), 0)
		self.assertEqual(payment_request.status, "Paid")

	def test_a_pending_refund_settles_from_its_webhook_and_a_replay_changes_nothing(self):
		payment_request = self.make_paid_request(1000)
		testing.set_next_refund_status("Pending")

		with testing.without_commits():
			payment_request.refund(250)
			refund = frappe.get_all(
				"Gateway Refund", {"payment_request": payment_request.name}, pluck="name"
			)[0]
			payment_request.reload()
			self.assertEqual(flt(payment_request.refund_amount), 0, "a pending refund is not money back yet")

			testing.send_refund_webhook(refund, "Processed")
			testing.send_refund_webhook(refund, "Processed")
			payment_request.reload()

		self.assertEqual(flt(payment_request.refund_amount), 250)
		self.assertEqual(payment_request.status, "Partially Refunded")

	def test_a_refund_raised_in_the_gateway_dashboard_is_recorded(self):
		payment_request = self.make_paid_request(1000)

		with testing.without_commits():
			refund_id = testing.send_external_refund_webhook(payment_request.name, 300)
			payment_request.reload()

		self.assertEqual(
			[(row.refund_id, flt(row.amount)) for row in self.get_refunds(payment_request)],
			[(refund_id, 300)],
		)
		self.assertEqual(flt(payment_request.refund_amount), 300)

	def test_a_payment_entry_refunds_its_gateway_once(self):
		payment_request = self.make_paid_request(1000)
		payment_entry = frappe._dict(
			name="ACC-PAY-TEST-0001",
			payment_type="Pay",
			reference_no=payment_request.order_ref,
			mode_of_payment=self.gateway,
			paid_amount=200,
		)

		with testing.without_commits():
			refund_on_payment_entry(payment_entry)
			refund_on_payment_entry(payment_entry)

		self.assertEqual(
			[(flt(row.amount), row.payment_entry) for row in self.get_refunds(payment_request)],
			[(200, "ACC-PAY-TEST-0001")],
		)

	def test_a_payment_entry_for_another_mode_of_payment_is_left_alone(self):
		payment_request = self.make_paid_request(1000)

		refund_on_payment_entry(
			frappe._dict(
				name="ACC-PAY-TEST-0002",
				payment_type="Pay",
				reference_no=payment_request.order_ref,
				mode_of_payment="Cash",
				paid_amount=200,
			)
		)

		self.assertEqual(self.get_refunds(payment_request), [])

	def test_the_return_endpoint_confirms_with_the_gateway_and_redirects(self):
		payment_request = self.make_request(redirect_to="/orders/1")
		self.assertEqual(payment_request.return_endpoint, RETURN_ENDPOINT)

		StubRazorpayClient.pay(payment_request.order_ref)
		frappe.local.response = frappe._dict()
		api.return_from_gateway(payment_request.name)

		self.assertEqual(frappe.local.response.location, "/orders/1")
		self.assertEqual(
			frappe.db.get_value("Gateway Payment Request", payment_request.name, "status"), "Paid"
		)

	def test_the_old_bwh_payments_webhook_url_routes_to_commera(self):
		self.assertEqual(
			frappe.get_hooks("override_whitelisted_methods")["bwh_payments.bwh_payments.webhook.handle"][-1],
			"commera.payment_gateways.api.handle_webhook",
		)
