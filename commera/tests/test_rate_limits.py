import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.order_link import send_order_link
from commera.api.reviews import update_review
from commera.api.signup import verify_checkout_otp, verify_login_otp


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

	def test_a_spent_method_does_not_block_another_with_the_same_limit(self):
		order_lookup = {"order_number": "SAL-ORD-ZZ-NONE", "email": "zz@example.com"}
		for _attempt in range(10):
			self.call(send_order_link, **order_lookup)

		with self.assertRaises(frappe.RateLimitExceededError):
			self.call(send_order_link, **order_lookup)

		with self.assertRaisesRegex(frappe.ValidationError, "Sign in to edit your review"):
			self.call(update_review, name="zz-none", rating=5)

	def test_email_keyed_methods_keep_their_own_attempts(self):
		email = f"zz-limits-{frappe.generate_hash(length=8)}@example.com"
		for _attempt in range(5):
			with self.assertRaisesRegex(frappe.ValidationError, "Invalid OTP"):
				self.call(verify_login_otp, email=email, otp="000000")

		with self.assertRaises(frappe.RateLimitExceededError):
			self.call(verify_login_otp, email=email, otp="000000")

		with self.assertRaisesRegex(frappe.ValidationError, "Invalid OTP"):
			self.call(verify_checkout_otp, email=email, otp="000000")
