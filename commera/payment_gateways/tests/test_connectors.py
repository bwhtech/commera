from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import frappe
from frappe.model.base_document import get_controller
from frappe.tests import IntegrationTestCase

from commera.payment_gateways import connectors
from commera.plugins.providers import ProviderNotRegisteredError

GATEWAY_SETTINGS = [
	"Razorpay Gateway Settings",
	"Stripe Gateway Settings",
	"Telr Gateway Settings",
	"Tabby Gateway Settings",
]


class TestPaymentConnectors(IntegrationTestCase):
	def test_commera_offers_its_four_gateways(self):
		self.assertEqual(connectors.get_connector_doctypes(), GATEWAY_SETTINGS)

	def test_each_single_declares_every_field_its_connector_reads(self):
		for doctype in GATEWAY_SETTINGS:
			missing = [
				field
				for field in get_controller(doctype).credential_fields
				if not frappe.get_meta(doctype).has_field(field)
			]
			self.assertEqual(missing, [], doctype)

	def register(self, doctypes: list[str]):
		get_hooks = frappe.get_hooks

		def get_hooks_with(hook=None, *args, **kwargs):
			if hook == "commera_hooks":
				return {**get_hooks(hook, *args, **kwargs), connectors.KIND: doctypes}
			return get_hooks(hook, *args, **kwargs)

		return patch.object(frappe, "get_hooks", side_effect=get_hooks_with)

	def test_an_unregistered_gateway_single_is_reported(self):
		with self.register(GATEWAY_SETTINGS[1:]), redirect_stdout(StringIO()) as output:
			connectors.validate_connectors()

		self.assertIn("Razorpay Gateway Settings implements the payment gateway contract", output.getvalue())

	def test_a_registered_doctype_that_is_not_a_gateway_stops_the_migrate(self):
		with (
			self.register([*GATEWAY_SETTINGS, "Commera Settings"]),
			self.assertRaises(ProviderNotRegisteredError),
		):
			connectors.validate_connectors()
