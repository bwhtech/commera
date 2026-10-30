# Copyright (c) 2026, Build With Hussain and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestPartnerShipment(IntegrationTestCase):
	def test_a_shipment_without_provider_refuses_carrier_calls(self):
		shipment = frappe.new_doc("Shipment")
		self.assertRaises(frappe.ValidationError, shipment.get_controller)

	def test_tracking_url_must_be_a_web_link(self):
		shipment = frappe.new_doc("Shipment")
		for tracking_url in ("javascript:alert(1)", "/track/123", "ftp://example.com/x"):
			shipment.tracking_url = tracking_url
			self.assertRaises(frappe.ValidationError, shipment.validate_tracking_url)

		shipment.tracking_url = "https://track.example.com/AWB123"
		shipment.validate_tracking_url()
