import frappe
from frappe.tests import IntegrationTestCase

from commera.shop_themes.tests import test_commera_starter_catalog
from commera.tests import test_cart_checkout


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
		frappe.set_user(self.create_shopper())
		self.addCleanup(frappe.set_user, "Administrator")

		with self.assertRaises(frappe.Redirect):
			self.render("pages/cart/cart.html", "/en/cart", checkout="1", discount="ZZSAVE")

		self.assertEqual(frappe.flags.redirect_location, "/en/cart/checkout?discount=ZZSAVE")

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
