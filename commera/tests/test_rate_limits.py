import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.order_link import send_order_link


class TestRateLimits(IntegrationTestCase):
	def setUp(self):
		frappe.local.request = Request(EnvironBuilder(path="/api/v2/method/commera").get_environ())
		self.addCleanup(delattr, frappe.local, "request")
		frappe.local.request_ip = f"10.{frappe.generate_hash(length=6)}"
		self.addCleanup(delattr, frappe.local, "request_ip")
		self.addCleanup(frappe.cache.delete_keys, f"rl:*{frappe.local.request_ip}*")
		frappe.set_user("Guest")
		self.addCleanup(frappe.set_user, "Administrator")

	def call(self, method, **kwargs):
		frappe.form_dict.clear()
		frappe.form_dict.update(kwargs)
		return method(**kwargs)

	def test_a_limited_method_refuses_past_its_limit(self):
		order_lookup = {"order_number": "SAL-ORD-ZZ-NONE", "email": "zz@example.com"}
		for _attempt in range(10):
			self.call(send_order_link, **order_lookup)

		with self.assertRaises(frappe.RateLimitExceededError):
			self.call(send_order_link, **order_lookup)
