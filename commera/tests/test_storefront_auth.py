from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.signup import MAX_OTP_ATTEMPTS
from commera.api.storefront import auth
from commera.core import get_otp_attempts_key, get_otp_key

CODE = "123456"
WRONG_CODE = "654321"


class TestStorefrontAuth(IntegrationTestCase):
	def setUp(self):
		self.email = f"zz-auth-{frappe.generate_hash(length=8)}@example.com"
		for purpose in ("login", "signup"):
			self.addCleanup(frappe.cache.delete_value, get_otp_key(self.email, purpose))
			self.addCleanup(frappe.cache.delete_value, get_otp_attempts_key(self.email, purpose))
		self.addCleanup(frappe.set_user, "Administrator")
		self.login_manager = MagicMock()
		self.login_manager.login_as.side_effect = frappe.set_user
		self.login_manager.logout.side_effect = lambda arg="", user=None: user or frappe.set_user("Guest")
		login_manager_patch = patch.object(frappe.local, "login_manager", self.login_manager, create=True)
		login_manager_patch.start()
		self.addCleanup(login_manager_patch.stop)
		developer_mode_patch = patch.dict(frappe.conf, {"developer_mode": 1})
		developer_mode_patch.start()
		self.addCleanup(developer_mode_patch.stop)
		frappe.set_user("Guest")

	def create_user(self, enabled=1) -> str:
		return (
			frappe.get_doc(
				{
					"doctype": "User",
					"email": self.email,
					"first_name": "Zz",
					"last_name": "Existing",
					"enabled": enabled,
					"send_welcome_email": 0,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def get_code(self, purpose: str):
		return frappe.cache.get_value(get_otp_key(self.email, purpose))

	def cache_code(self, purpose: str):
		frappe.cache.set_value(get_otp_key(self.email, purpose), CODE, expires_in_sec=60)

	def test_login_answers_alike_and_mails_only_an_account(self):
		unknown_answer = auth.send_login_code(self.email)
		self.assertIsNone(self.get_code("login"))

		self.create_user()
		known_answer = auth.send_login_code(f"  {self.email.upper()} ")

		self.assertEqual(unknown_answer, known_answer)
		self.assertTrue(self.get_code("login"))

	def test_a_login_code_signs_in_once(self):
		user = self.create_user()
		self.cache_code("login")

		profile = auth.log_in(self.email.upper(), CODE)

		self.assertEqual(frappe.session.user, user)
		self.assertEqual(profile["email"], self.email)
		with self.assertRaisesRegex(frappe.ValidationError, "Invalid code"):
			auth.log_in(self.email, CODE)

	def test_a_code_only_works_for_its_own_purpose(self):
		self.create_user()
		self.cache_code("signup")

		with self.assertRaisesRegex(frappe.ValidationError, "Invalid code"):
			auth.log_in(self.email, CODE)
		self.login_manager.login_as.assert_not_called()

	def test_wrong_guesses_use_up_the_code(self):
		self.create_user()
		self.cache_code("login")

		for _attempt in range(MAX_OTP_ATTEMPTS - 1):
			with self.assertRaisesRegex(frappe.ValidationError, "Invalid code"):
				auth.log_in(self.email, WRONG_CODE)
		with self.assertRaisesRegex(frappe.ValidationError, "Too many wrong codes"):
			auth.log_in(self.email, WRONG_CODE)

		self.assertIsNone(self.get_code("login"))
		with self.assertRaisesRegex(frappe.ValidationError, "Invalid code"):
			auth.log_in(self.email, CODE)

	def test_a_new_code_resets_the_wrong_guesses(self):
		self.create_user()
		self.cache_code("login")
		for _attempt in range(MAX_OTP_ATTEMPTS - 1):
			with self.assertRaises(frappe.ValidationError):
				auth.log_in(self.email, WRONG_CODE)

		auth.send_login_code(self.email)
		with self.assertRaisesRegex(frappe.ValidationError, "Invalid code"):
			auth.log_in(self.email, WRONG_CODE)

		self.assertTrue(self.get_code("login"))

	def test_a_disabled_account_cannot_sign_in(self):
		self.create_user(enabled=0)
		self.cache_code("login")

		with self.assertRaises(frappe.AuthenticationError):
			auth.log_in(self.email, CODE)
		self.login_manager.login_as.assert_not_called()

	def test_signup_creates_the_account_and_signs_in(self):
		auth.send_signup_code(self.email.upper(), "Asha", "Menon")
		frappe.cache.set_value(get_otp_key(self.email, "signup"), CODE, expires_in_sec=60)

		profile = auth.sign_up(self.email, "Asha", CODE, "Menon")

		self.assertEqual(frappe.session.user, self.email)
		self.assertEqual((profile["email"], profile["full_name"]), (self.email, "Asha Menon"))

	def test_signup_for_an_existing_account_answers_alike_and_signs_in_to_it(self):
		new_email_answer = auth.send_signup_code(self.email, "Asha", "Menon")
		user = self.create_user()
		existing_email_answer = auth.send_signup_code(self.email, "Asha", "Menon")
		self.cache_code("signup")

		profile = auth.sign_up(self.email, "Asha", CODE, "Menon")

		self.assertEqual(new_email_answer, existing_email_answer)
		self.assertEqual(frappe.session.user, user)
		self.assertEqual(profile["full_name"], "Zz Existing")

	def test_an_account_created_meanwhile_is_a_clear_error(self):
		self.create_user()
		self.cache_code("signup")

		with (
			patch("commera.sdk.auth.get_account", return_value=None),
			self.assertRaisesRegex(frappe.ValidationError, "already registered"),
		):
			auth.sign_up(self.email, "Asha", CODE, "Menon")

	def test_signup_checks_the_names_and_the_email(self):
		with self.assertRaisesRegex(frappe.ValidationError, "first name"):
			auth.send_signup_code(self.email, " ", "Menon")
		with self.assertRaises(frappe.InvalidEmailAddressError):
			auth.send_signup_code(f"{self.email}, other@example.com", "Asha")
		self.assertIsNone(self.get_code("signup"))

	def test_log_out_returns_to_guest(self):
		frappe.set_user(self.create_user())

		auth.log_out()

		self.assertEqual(frappe.session.user, "Guest")
