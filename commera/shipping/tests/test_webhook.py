import frappe
from frappe.tests import IntegrationTestCase

from commera.shipping import webhook

OLD_WEBHOOK_METHOD = "bwh_shipping.bwh_shipping.webhook.handle"


class TestWebhookRoute(IntegrationTestCase):
	def test_the_bwh_shipping_url_still_reaches_the_webhook(self):
		handler = frappe.get_attr(frappe.override_whitelisted_method(OLD_WEBHOOK_METHOD))

		self.assertIs(handler, webhook.handle)
		self.assertIn(handler, frappe.guest_methods)
