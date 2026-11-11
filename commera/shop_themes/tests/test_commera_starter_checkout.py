import frappe
from frappe.tests import IntegrationTestCase

from commera.shop_themes.tests import test_commera_starter_catalog
from commera.tests import test_cart_checkout
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_markets import UAE, make_market, use_markets


class IntegrationTestCommeraStarterCheckout(IntegrationTestCase):
	setUp = test_commera_starter_catalog.IntegrationTestCommeraStarterCatalog.setUp
	restore_locals = test_commera_starter_catalog.IntegrationTestCommeraStarterCatalog.restore_locals
	render = test_commera_starter_catalog.IntegrationTestCommeraStarterCatalog.render
	create_shopper = test_cart_checkout.TestCartCheckout.create_shopper

	def test_the_checkout_offers_the_address_form_and_the_order_summary(self):
		frappe.set_user("Guest")
		self.addCleanup(frappe.set_user, "Administrator")

		status, html = self.render("pages/cart/checkout.html", "/en/cart/checkout")

		self.assertEqual(status, 200)
		self.assertIn("x-data='checkout(", html)
		self.assertIn('x-model="forms.shipping.address_line1"', html)
		self.assertIn('x-model="forms.billing.address_line1"', html)
		self.assertIn('x-data="order_summary"', html)
		self.assertIn("summary?.taxes", html)
		self.assertIn("noindex", html)

	def test_a_signed_in_shopper_back_from_the_checkout_handoff_goes_on_to_checkout(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		frappe.set_user(self.create_shopper())
		self.addCleanup(frappe.set_user, "Administrator")

		with self.assertRaises(frappe.Redirect):
			self.render("pages/cart/cart.html", "/ar/cart", checkout="1", discount="ZZSAVE")

		self.assertEqual(frappe.flags.redirect_location, "/ar/cart/checkout?discount=ZZSAVE")

	def test_a_guest_on_the_cart_page_stays_on_it(self):
		frappe.set_user("Guest")
		self.addCleanup(frappe.set_user, "Administrator")

		status, _html = self.render("pages/cart/cart.html", "/en/cart", checkout="1")

		self.assertEqual(status, 200)

	def test_the_confirmation_page_completes_the_payment_in_the_browser(self):
		status, html = self.render(
			"pages/account/orders/confirmation.html", "/en/account/orders/confirmation"
		)

		self.assertEqual(status, 200)
		self.assertIn('x-data="order_confirmation"', html)
		self.assertIn("noindex", html)

	def test_an_unavailable_line_names_the_country_and_blocks_checkout(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		use_markets(self)
		make_market("Gulf", [UAE], "ar", ["en"], handle="gulf")
		frappe.set_user("Guest")
		self.addCleanup(frappe.set_user, "Administrator")

		for template, path in (
			("pages/cart/cart.html", "/en-ae/cart"),
			("pages/cart/checkout.html", "/en-ae/cart/checkout"),
		):
			with self.subTest(path):
				status, html = self.render(template, path)

				self.assertEqual(status, 200)
				self.assertIn('x-show="line.available === false"', html)
				self.assertIn("Not available in United Arab Emirates", html)
				self.assertIn("Remove the items not available in United Arab Emirates to check out.", html)
				self.assertIn(':disabled="$store.cart.busy || $store.cart.has_unavailable"', html)
				self.assertIn("removed_codes", html)

		self.assertIn('@click="$store.cart.remove(line)"', html)
		self.assertIn("!payment_method || $store.cart.has_unavailable", html)
