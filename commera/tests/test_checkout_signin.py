# Copyright (c) 2026, company@bwhstudios.com and Contributors
# See license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.payments import replace_placeholder_names
from commera.api.signup import send_checkout_otp, verify_checkout_otp
from commera.core import _create_party_for_user

OTP = "123456"


class TestCheckoutSignin(IntegrationTestCase):
	def setUp(self):
		self.local_part = f"zz-checkout-{frappe.generate_hash(length=8)}"
		self.email = f"{self.local_part}@example.com"
		self.addCleanup(frappe.cache.delete_value, f"otp:{self.email}")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")
		self.login_manager = MagicMock()
		login_manager_patch = patch.object(frappe.local, "login_manager", self.login_manager, create=True)
		login_manager_patch.start()
		self.addCleanup(login_manager_patch.stop)

	def create_user(self, first_name, last_name="", enabled=1):
		return frappe.get_doc(
			{
				"doctype": "User",
				"email": self.email,
				"first_name": first_name,
				"last_name": last_name,
				"enabled": enabled,
			}
		).insert(ignore_permissions=True)

	def cache_otp(self):
		frappe.cache.set_value(f"otp:{self.email}", OTP, expires_in_sec=60)

	def test_send_checkout_otp_answers_alike_for_new_and_existing_emails(self):
		with patch.dict(frappe.conf, {"developer_mode": 1}):
			response_for_new_email = send_checkout_otp(self.email)
			first_code = frappe.cache.get_value(f"otp:{self.email}")

			self.create_user("Zz")
			response_for_existing_email = send_checkout_otp(self.email)

		self.assertTrue(first_code)
		self.assertTrue(frappe.cache.get_value(f"otp:{self.email}"))
		self.assertEqual(response_for_new_email, response_for_existing_email)

	def test_send_checkout_otp_keys_the_code_on_the_lowercased_email(self):
		with patch.dict(frappe.conf, {"developer_mode": 1}):
			send_checkout_otp(f"  {self.email.upper()} ")

		self.assertTrue(frappe.cache.get_value(f"otp:{self.email}"))

	def test_verify_checkout_otp_creates_a_user_named_after_the_email_and_signs_in(self):
		self.cache_otp()

		verify_checkout_otp(self.email.upper(), OTP)

		user = frappe.get_doc("User", self.email)
		self.assertEqual(user.first_name, self.local_part)
		self.assertIn("Customer", frappe.get_roles(self.email))
		self.login_manager.login_as.assert_called_once_with(self.email)

	def test_verify_checkout_otp_signs_an_existing_user_in_without_renaming_them(self):
		self.create_user("Asha")
		self.cache_otp()

		verify_checkout_otp(self.email, OTP)

		self.assertEqual(frappe.db.get_value("User", self.email, "first_name"), "Asha")
		self.login_manager.login_as.assert_called_once_with(self.email)

	def test_verify_checkout_otp_refuses_a_wrong_code(self):
		self.cache_otp()

		with self.assertRaisesRegex(frappe.ValidationError, "Invalid OTP"):
			verify_checkout_otp(self.email, "654321")

		self.assertFalse(frappe.db.exists("User", self.email))
		self.login_manager.login_as.assert_not_called()

	def test_verify_checkout_otp_refuses_a_disabled_account(self):
		self.create_user("Zz", enabled=0)
		self.cache_otp()

		with self.assertRaises(frappe.AuthenticationError):
			verify_checkout_otp(self.email, OTP)

		self.login_manager.login_as.assert_not_called()

	def sign_in_shopper(self, first_name, last_name=""):
		self.create_user(first_name, last_name)
		customer = _create_party_for_user(self.email)
		contact = frappe.get_doc("Contact", {"email_id": self.email})
		frappe.set_user(self.email)
		quotation = frappe._dict(
			party_name=customer.name, customer_name=customer.customer_name, contact_email=self.email
		)
		return customer, contact, quotation

	def test_billing_name_replaces_the_placeholder_everywhere(self):
		customer, contact, quotation = self.sign_in_shopper(self.local_part)

		replace_placeholder_names(quotation, contact, {"first_name": " Asha ", "last_name": "Rao"})

		self.assertEqual(frappe.session.user, self.email)
		self.assertEqual((contact.first_name, contact.last_name), ("Asha", "Rao"))
		self.assertEqual(quotation.customer_name, "Asha Rao")
		self.assertEqual(frappe.db.get_value("Customer", customer.name, "customer_name"), "Asha Rao")
		self.assertEqual(
			frappe.db.get_value("User", self.email, ["first_name", "last_name"]), ("Asha", "Rao")
		)

	def test_billing_name_never_overwrites_a_real_name(self):
		customer, contact, quotation = self.sign_in_shopper("Asha", "Rao")

		replace_placeholder_names(quotation, contact, {"first_name": "Someone", "last_name": "Else"})

		self.assertEqual(quotation.customer_name, "Asha Rao")
		self.assertEqual(frappe.db.get_value("Customer", customer.name, "customer_name"), "Asha Rao")
		self.assertEqual(frappe.db.get_value("User", self.email, "first_name"), "Asha")
