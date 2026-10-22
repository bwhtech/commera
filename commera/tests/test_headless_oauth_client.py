import frappe
from frappe.tests import IntegrationTestCase


class TestHeadlessOAuthClient(IntegrationTestCase):
	def save_storefront_url(self, url: str | None):
		settings = frappe.get_doc("Commera Settings")
		settings.headless_storefront_url = url
		settings.save(ignore_permissions=True)
		return settings

	def test_a_storefront_url_sets_up_a_client_that_signs_shoppers_in(self):
		settings = self.save_storefront_url("https://shop.example.com/")

		client = frappe.get_doc("OAuth Client", settings.headless_oauth_client)
		self.assertEqual(settings.headless_storefront_url, "https://shop.example.com")
		self.assertEqual(client.redirect_uris, "https://shop.example.com/account/authorize")
		self.assertEqual(client.default_redirect_uri, client.redirect_uris)
		self.assertEqual(
			(client.app_name, client.grant_type, client.response_type, client.skip_authorization),
			("Commera Storefront", "Authorization Code", "Code", 1),
		)
		self.assertEqual(client.token_endpoint_auth_method, "Client Secret Post")
		self.assertEqual([row.role for row in client.allowed_roles], ["Customer"])
		self.assertTrue(client.client_secret)

	def test_a_new_url_moves_the_same_client(self):
		first = self.save_storefront_url("https://old.example.com").headless_oauth_client

		settings = self.save_storefront_url("https://new.example.com")

		self.assertEqual(settings.headless_oauth_client, first)
		self.assertEqual(
			frappe.db.get_value("OAuth Client", first, "redirect_uris"),
			"https://new.example.com/account/authorize",
		)

	def test_clearing_the_url_keeps_the_client(self):
		client = self.save_storefront_url("https://keep.example.com").headless_oauth_client

		settings = self.save_storefront_url(None)

		self.assertEqual(settings.headless_oauth_client, client)
		self.assertEqual(
			frappe.db.get_value("OAuth Client", client, "redirect_uris"),
			"https://keep.example.com/account/authorize",
		)

	def test_a_url_that_is_not_web_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.save_storefront_url("ftp://shop.example.com")
