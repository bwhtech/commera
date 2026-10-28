# Copyright (c) 2026, Build With Hussain and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from commera.shipping.units import DEFAULT_VOLUMETRIC_DIVISOR


class TestPartnerShipment(IntegrationTestCase):
	def test_request_without_provider_uses_default_divisor(self):
		request = frappe.new_doc("Shipping Request")
		self.assertEqual(request.get_volumetric_divisor(), DEFAULT_VOLUMETRIC_DIVISOR)

	def test_request_without_provider_refuses_carrier_calls(self):
		request = frappe.new_doc("Shipping Request")
		self.assertRaises(frappe.ValidationError, request.get_controller)

	def test_tracking_url_must_be_a_web_link(self):
		request = frappe.new_doc("Shipping Request")
		for tracking_url in ("javascript:alert(1)", "/track/123", "ftp://example.com/x"):
			request.tracking_url = tracking_url
			self.assertRaises(frappe.ValidationError, request.validate_tracking_url)

		request.tracking_url = "https://track.example.com/AWB123"
		request.validate_tracking_url()

	def test_only_a_carrier_shipment_needs_a_pickup_address(self):
		request = frappe.new_doc("Shipping Request")
		request.validate_origin_address()

		request.provider = "Any Carrier"
		self.assertRaises(frappe.ValidationError, request.validate_origin_address)
