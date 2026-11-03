# Copyright (c) 2025, company@bwhstudios.com and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

SETTINGS = "Commera Settings"
NO_GATEWAYS = patch(
	"commera.commera_ecommerce.doctype.commera_settings.commera_settings.get_available_payment_modes",
	return_value=[],
)


class TestCommeraSettings(IntegrationTestCase):
	def setUp(self):
		was_enabled = frappe.db.get_single_value(SETTINGS, "cod_enabled")
		self.addCleanup(frappe.db.set_single_value, SETTINGS, "cod_enabled", was_enabled)

	def test_cash_on_delivery_is_off_by_default(self):
		self.assertFalse(frappe.get_meta(SETTINGS).get_field("cod_enabled").default)

	def test_a_store_without_payment_methods_can_still_save(self):
		frappe.db.set_single_value(SETTINGS, "cod_enabled", 0)
		settings = frappe.get_doc(SETTINGS)
		settings.store_category = "Fashion"
		with NO_GATEWAYS:
			settings.save()

	def test_turning_off_the_last_payment_method_is_refused(self):
		frappe.db.set_single_value(SETTINGS, "cod_enabled", 1)
		settings = frappe.get_doc(SETTINGS)
		settings.cod_enabled = 0
		with NO_GATEWAYS, self.assertRaises(frappe.ValidationError):
			settings.save()
