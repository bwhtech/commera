import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.data import flt

from commera.patches import create_gateway_refunds_from_refund_totals, move_bwh_payments_into_commera

PAYMENT_DOCTYPES = (
	"Gateway Payment Request",
	"Payment Gateway Profile",
	"Stripe Gateway Settings",
	"Razorpay Gateway Settings",
	"Telr Gateway Settings",
	"Tabby Gateway Settings",
)
GATEWAY = "Old Stripe"


class TestMoveBwhPaymentsIntoCommera(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.clear_cache)
		self.addCleanup(frappe.db.rollback)

	def rebuild_old_module(self):
		frappe.get_doc(
			{"doctype": "Module Def", "module_name": "BWH Payments", "app_name": "bwh_payments"}
		).db_insert()
		for doctype in PAYMENT_DOCTYPES:
			frappe.db.set_value("DocType", doctype, "module", "BWH Payments")

	def test_the_payment_doctypes_move_to_commera_and_bwh_payments_leaves_the_site(self):
		self.rebuild_old_module()
		installed_apps = [*frappe.get_installed_apps(), "bwh_payments"]

		with (
			patch.object(frappe, "get_installed_apps", return_value=installed_apps),
			patch.object(move_bwh_payments_into_commera, "remove_from_installed_apps") as remove_app,
		):
			move_bwh_payments_into_commera.execute()

		remove_app.assert_called_once_with("bwh_payments")
		self.assertFalse(frappe.db.exists("Module Def", "BWH Payments"))
		self.assertEqual(frappe.db.get_value("Module Def", "Payment Gateways", "app_name"), "commera")
		for doctype in PAYMENT_DOCTYPES:
			self.assertEqual(frappe.db.get_value("DocType", doctype, "module"), "Payment Gateways", doctype)

	def test_a_site_that_never_had_bwh_payments_is_left_alone(self):
		with patch.object(move_bwh_payments_into_commera, "remove_from_installed_apps") as remove_app:
			move_bwh_payments_into_commera.execute()

		remove_app.assert_not_called()


class TestCreateGatewayRefundsFromRefundTotals(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)

	def make_old_request(self, amount: float, refund_amount: float, refund_id: str | None, status: str):
		payment_request = frappe.get_doc(
			{
				"doctype": "Gateway Payment Request",
				"gateway": GATEWAY,
				"amount": amount,
				"currency_code": "INR",
				"ref_doctype": "ToDo",
				"ref_docname": "old-order",
				"order_ref": f"cs_old_{frappe.generate_hash(length=8)}",
				"status": status,
				"refund_amount": refund_amount,
				"refund_id": refund_id,
			}
		)
		payment_request.set_new_name()
		payment_request.db_insert()
		return payment_request

	def log_old_refund(self, payment_request, amount: float, status: str = "Completed"):
		frappe.get_doc(
			{
				"doctype": "Integration Request",
				"integration_request_service": f"{GATEWAY} Refund",
				"reference_doctype": "Gateway Payment Request",
				"reference_docname": payment_request.name,
				"status": status,
				"data": json.dumps({"gateway_payment_request": payment_request.name, "amount": amount}),
			}
		).insert(ignore_permissions=True)

	def get_refunds(self, payment_request) -> list[tuple]:
		return [
			(row.refund_id, flt(row.amount), row.status)
			for row in frappe.get_all(
				"Gateway Refund",
				filters={"payment_request": payment_request.name},
				fields=["refund_id", "amount", "status"],
				order_by="refund_id asc",
			)
		]

	def test_each_logged_refund_becomes_a_processed_row(self):
		payment_request = self.make_old_request(1000, 700, "re_1,re_2", "Partially Refunded")
		self.log_old_refund(payment_request, 300)
		self.log_old_refund(payment_request, 50, status="Failed")
		self.log_old_refund(payment_request, 400)

		create_gateway_refunds_from_refund_totals.execute()

		self.assertEqual(
			self.get_refunds(payment_request), [("re_1", 300, "Processed"), ("re_2", 400, "Processed")]
		)
		self.assertEqual(
			flt(frappe.db.get_value("Gateway Payment Request", payment_request.name, "refund_amount")), 700
		)

	def test_a_total_the_logs_do_not_explain_becomes_one_row(self):
		payment_request = self.make_old_request(1000, 1000, "re_1,re_2", "Refunded")
		self.log_old_refund(payment_request, 300)

		create_gateway_refunds_from_refund_totals.execute()

		self.assertEqual(self.get_refunds(payment_request), [(None, 1000, "Processed")])

	def test_a_single_refund_keeps_its_id_without_logs(self):
		payment_request = self.make_old_request(500, 500, "re_only", "Refunded")

		create_gateway_refunds_from_refund_totals.execute()

		self.assertEqual(self.get_refunds(payment_request), [("re_only", 500, "Processed")])

	def test_running_twice_adds_nothing(self):
		payment_request = self.make_old_request(1000, 250, "re_1", "Partially Refunded")
		untouched = self.make_old_request(1000, 0, None, "Paid")

		create_gateway_refunds_from_refund_totals.execute()
		create_gateway_refunds_from_refund_totals.execute()

		self.assertEqual(self.get_refunds(payment_request), [("re_1", 250, "Processed")])
		self.assertEqual(self.get_refunds(untouched), [])
