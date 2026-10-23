import frappe
from frappe.tests import IntegrationTestCase

from commera.tests.test_order_access import make_website_user
from commera.www import storefront_login

AUTHORIZE_PATH = "/api/method/frappe.integrations.oauth2.authorize?client_id=abc&response_type=code"


class TestStorefrontLogin(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		self.addCleanup(frappe.local.flags.pop, "redirect_location", None)

	def open_page(self, user: str = "Guest", **query) -> frappe._dict:
		frappe.set_user(user)
		frappe.local.form_dict = frappe._dict(query)
		context = frappe._dict()
		storefront_login.get_context(context)
		return context

	def test_a_guest_sees_the_form_that_goes_on_to_the_path(self):
		context = self.open_page(**{"redirect-to": AUTHORIZE_PATH})

		self.assertEqual(context.redirect_to, AUTHORIZE_PATH)
		self.assertIsNone(context.signed_in_user)

	def test_a_target_off_this_site_goes_home(self):
		for target in ("https://evil.example.com", "//evil.example.com", "/\\evil.example.com", "/\t/evil"):
			with self.subTest(target):
				self.assertEqual(self.open_page(**{"redirect-to": target}).redirect_to, "/")

	def test_a_signed_in_shopper_goes_straight_on(self):
		with self.assertRaises(frappe.Redirect):
			self.open_page(make_website_user(), **{"redirect-to": AUTHORIZE_PATH})

		self.assertEqual(frappe.local.flags.redirect_location, AUTHORIZE_PATH)

	def test_a_sign_in_prompt_shows_the_form_to_a_signed_in_shopper(self):
		shopper = make_website_user()

		context = self.open_page(shopper, prompt="login", **{"redirect-to": AUTHORIZE_PATH})

		self.assertEqual((context.redirect_to, context.signed_in_user), (AUTHORIZE_PATH, shopper))
