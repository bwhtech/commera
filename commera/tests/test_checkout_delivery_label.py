import json
import re

import frappe

from commera.tests.test_cart_currency import CartCurrencyTestCase
from commera.tests.test_delivery_option_charges import make_store_rule, set_store_rule

CHECKOUT_CONFIG = re.compile(r"x-data='summer_checkout\((.*?)\)'>")


class TestSummerCheckoutDeliveryLabel(CartCurrencyTestCase):
	"""The cart is checked out before the store charges delivery; its rule is ₹500 below ₹100,000."""

	def setUp(self):
		super().setUp()
		self.addCleanup(set_store_rule, frappe.db.get_single_value("Commera Settings", "shipping_rule"))
		set_store_rule(None)

	def test_a_market_checkout_shows_the_delivery_charge_in_the_cart_currency(self):
		self.checkout_quotation("/en-ae/cart/checkout")
		self.charge_below(100000)

		summary = self.rendered_summary("/en-ae/cart/checkout")

		# ₹500 at 20 to the market currency.
		self.assertEqual(summary["shipping"], 25)
		self.assertEqual(summary["total"], 3499 + 25)

	def test_the_primary_market_checkout_shows_the_delivery_charge(self):
		self.checkout_quotation("/cart/checkout")
		self.charge_below(100000)

		summary = self.rendered_summary("/cart/checkout")

		self.assertEqual(summary["shipping"], 500)
		self.assertEqual(summary["total"], 80 + 500)

	def test_a_cart_above_the_free_delivery_band_is_free(self):
		self.checkout_quotation("/en-ae/cart/checkout")
		self.charge_below(50000)

		summary = self.rendered_summary("/en-ae/cart/checkout")

		self.assertEqual(summary["shipping"], 0)
		self.assertEqual(summary["total"], 3499)

	def charge_below(self, threshold):
		make_store_rule(
			[
				{"from_value": 0, "to_value": threshold - 0.01, "shipping_amount": 500},
				{"from_value": threshold, "to_value": 0, "shipping_amount": 0, "free_shipping": 1},
			]
		)

	def rendered_summary(self, path):
		html = self.render_summer("pages/cart/checkout.html", path)
		return json.loads(CHECKOUT_CONFIG.search(html).group(1))["summary"]
