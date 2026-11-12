from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from commera.api.storefront.products import get_wishlist_prices


class TestWishlistPrices(FrappeTestCase):
	def test_guest_endpoint_and_cap(self):
		self.assertIn(get_wishlist_prices, frappe.whitelisted)
		self.assertIn(get_wishlist_prices, frappe.guest_methods)
		for handles in (["shoe"] * 101, {"shoe": 1}, [1]):
			with self.assertRaises(frappe.ValidationError):
				get_wishlist_prices(handles)

	def test_only_published_cards_are_returned(self):
		card = dict(handle="shoe", price=30, compare_at_price=40, currency="AED", available=True)
		with (
			patch("frappe.get_all", return_value=["published"]) as query,
			patch("commera.sdk.catalog.get_product_cards_for", return_value=[card]) as cards,
		):
			result = get_wishlist_prices('["shoe", "private"]')
			self.assertEqual(query.call_args.kwargs["filters"]["is_published"], 1)
			cards.assert_called_once_with(["published"])
			self.assertEqual(result[0], card)
			self.assertFalse(result[1]["available"])
			self.assertIsNone(result[1]["price"])
