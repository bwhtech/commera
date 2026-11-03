import sys
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.www import commera as dashboard

CLOUD_SETTINGS = "frappe.integrations.frappe_providers.cloud_settings"


class TestCloudSettingsBoot(IntegrationTestCase):
	def get_boot(self) -> frappe._dict:
		with self.set_user("Administrator"), patch.object(frappe.db, "commit"):
			return dashboard.get_boot()

	def test_a_site_without_pilot_credentials_hides_cloud_settings(self):
		with patch.dict(frappe.local.conf, {"pilot_endpoint": None, "pilot_auth_token": None}):
			self.assertEqual(self.get_boot().cloud_settings, {"enabled": False})

	def test_boot_passes_the_provider_context_through(self):
		context = {"enabled": True, "site_name": frappe.local.site}
		with patch(f"{CLOUD_SETTINGS}.get_boot_context", return_value=context):
			self.assertEqual(self.get_boot().cloud_settings, context)

	def test_the_dashboard_opens_on_a_frappe_without_cloud_settings(self):
		# a None entry makes the import fail, as it does on frappe v15
		with patch.dict(sys.modules, {CLOUD_SETTINGS: None}):
			self.assertEqual(self.get_boot().cloud_settings, {"enabled": False})
