import frappe
from frappe.model.base_document import get_controller
from frappe.tests import IntegrationTestCase

from commera.payment_gateways import connectors

GATEWAY_SETTINGS = [
	"Razorpay Gateway Settings",
	"Stripe Gateway Settings",
	"Telr Gateway Settings",
	"Tabby Gateway Settings",
]


class TestPaymentConnectors(IntegrationTestCase):
	def test_each_single_declares_every_field_its_connector_reads(self):
		for doctype in GATEWAY_SETTINGS:
			missing = [
				field
				for field in get_controller(doctype).credential_fields
				if not frappe.get_meta(doctype).has_field(field)
			]
			self.assertEqual(missing, [], doctype)

	def test_bwh_payments_cannot_be_installed_alongside_commera(self):
		self.assertIn(
			"commera.payment_gateways.connectors.refuse_bwh_payments", frappe.get_hooks("before_app_install")
		)
		with self.assertRaises(frappe.ValidationError):
			connectors.refuse_bwh_payments("bwh_payments")
		connectors.refuse_bwh_payments("hrms")
