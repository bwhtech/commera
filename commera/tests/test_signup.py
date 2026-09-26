# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.signup import send_login_otp, send_signup_otp, verify_signup_otp

OTP = "123456"


class TestSignup(IntegrationTestCase):
	def setUp(self):
		self.email = f"zz-signup-{frappe.generate_hash(length=8)}@example.com"
		self.addCleanup(frappe.cache.delete_value, f"otp:{self.email}")
		self.addCleanup(frappe.db.rollback)
		self.first_name_length = (
			frappe.get_meta("User").get_field("first_name").length or frappe.db.VARCHAR_LEN
		)

	def get_cached_otp(self):
		return frappe.cache.get_value(f"otp:{self.email}")

	def test_send_signup_otp_caches_a_code_for_a_valid_signup(self):
		with patch.dict(frappe.conf, {"developer_mode": 1}):
			send_signup_otp(self.email, "Zz", "Shopper")

		self.assertTrue(self.get_cached_otp())

	def test_send_signup_otp_rejects_a_first_name_the_user_cannot_hold(self):
		too_long = "A" * (self.first_name_length + 1)

		with self.assertRaisesRegex(
			frappe.ValidationError, f"First Name cannot be longer than {self.first_name_length}"
		):
			send_signup_otp(self.email, too_long, "Shopper")

		self.assertIsNone(self.get_cached_otp())

	def test_send_signup_otp_rejects_names_whose_full_name_is_too_long(self):
		half = "A" * self.first_name_length

		with self.assertRaisesRegex(frappe.ValidationError, "Full Name cannot be longer than"):
			send_signup_otp(self.email, half, half)

		self.assertIsNone(self.get_cached_otp())

	def test_send_signup_otp_rejects_a_blank_first_name(self):
		with self.assertRaisesRegex(frappe.ValidationError, "first name"):
			send_signup_otp(self.email, "   ", "Shopper")

		self.assertIsNone(self.get_cached_otp())

	def test_send_signup_otp_rejects_an_invalid_email(self):
		for email in ("not-an-email", "a@example.com, b@example.com", "Name <a@example.com>"):
			with self.subTest(email=email):
				with self.assertRaises(frappe.InvalidEmailAddressError):
					send_signup_otp(email, "Zz", "Shopper")

				self.assertIsNone(frappe.cache.get_value(f"otp:{email}"))

	def test_send_login_otp_caches_a_code_for_an_existing_user(self):
		frappe.get_doc({"doctype": "User", "email": self.email, "first_name": "Zz"}).insert(
			ignore_permissions=True
		)

		with patch.dict(frappe.conf, {"developer_mode": 1}):
			send_login_otp(self.email)

		self.assertTrue(self.get_cached_otp())

	def test_send_login_otp_rejects_an_unknown_email(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Invalid login ID"):
			send_login_otp(self.email)

		self.assertIsNone(self.get_cached_otp())

	def test_send_login_otp_rejects_an_invalid_email(self):
		for email in ("a@example.com, b@example.com", "Name <a@example.com>"):
			with self.subTest(email=email):
				with self.assertRaises(frappe.InvalidEmailAddressError):
					send_login_otp(email)

				self.assertIsNone(frappe.cache.get_value(f"otp:{email}"))

	def test_verify_signup_otp_keeps_the_code_when_the_name_is_too_long(self):
		frappe.cache.set_value(f"otp:{self.email}", OTP, expires_in_sec=60)
		too_long = "A" * (self.first_name_length + 1)

		with self.assertRaisesRegex(frappe.ValidationError, "First Name cannot be longer than"):
			verify_signup_otp(self.email, too_long, "Shopper", OTP)

		self.assertEqual(str(self.get_cached_otp()), OTP)
		self.assertFalse(frappe.db.exists("User", self.email))
