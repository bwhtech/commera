from unittest.mock import patch

import frappe

from commera.api.storefront import wishlist as wishlist_api
from commera.sdk import wishlist
from commera.sdk.types import Wishlist
from commera.tests.test_order_access import make_website_user
from commera.tests.test_product_details import ProductDetailPriceTestCase


class TestSdkWishlist(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.set_user, "Administrator")
		self.route = self.make_priced_variant("WISH", default_rate=40)
		self.product = frappe.db.get_value("Style Attribute Variant", {"route": self.route})
		self.shopper = make_website_user()

	def test_a_shopper_adds_and_removes_a_product(self):
		frappe.set_user(self.shopper)

		added = wishlist.add_to_wishlist(self.product)
		removed = wishlist.remove_from_wishlist(self.product)

		self.assertEqual(set(added), Wishlist.__required_keys__)
		self.assertEqual([card["handle"] for card in added["products"]], [self.route])
		self.assertEqual(added["count"], 1)
		self.assertEqual(removed, {"products": [], "count": 0})

	def test_a_product_is_added_by_its_handle_and_kept_once(self):
		frappe.set_user(self.shopper)

		wishlist.add_to_wishlist(self.route)
		result = wishlist_api.add_to_wishlist(self.product)

		self.assertEqual(result["count"], 1)
		self.assertEqual(frappe.db.count("Commera Wishlist Item", {"user": self.shopper}), 1)

	def test_a_second_tap_racing_the_first_saves_no_duplicate(self):
		frappe.set_user(self.shopper)
		wishlist.add_to_wishlist(self.product)
		frappe.clear_messages()

		with patch("commera.sdk.wishlist.frappe.db.exists", return_value=None):
			result = wishlist.add_to_wishlist(self.product)

		self.assertEqual(result["count"], 1)
		self.assertEqual(frappe.db.count("Commera Wishlist Item", {"user": self.shopper}), 1)
		self.assertEqual(frappe.get_message_log(), [])

	def test_an_unpublished_product_is_refused(self):
		frappe.db.set_value("Style Attribute Variant", self.product, "is_published", 0)
		frappe.set_user(self.shopper)

		with self.assertRaises(frappe.DoesNotExistError):
			wishlist.add_to_wishlist(self.product)

	def test_a_product_unpublished_later_drops_out(self):
		frappe.set_user(self.shopper)
		wishlist.add_to_wishlist(self.product)
		frappe.db.set_value("Style Attribute Variant", self.product, "is_published", 0)

		self.assertEqual(wishlist.get_wishlist(), {"products": [], "count": 0})

	def test_an_empty_wishlist_lists_no_products(self):
		frappe.set_user(self.shopper)

		self.assertEqual(wishlist_api.get_wishlist(), {"products": [], "count": 0})

	def test_a_guest_is_refused(self):
		frappe.set_user("Guest")

		for call in (wishlist.get_wishlist, lambda: wishlist.add_to_wishlist(self.product)):
			with self.subTest(call=call), self.assertRaises(frappe.PermissionError):
				call()

	def test_a_shopper_never_sees_or_removes_another_shoppers_wishlist(self):
		frappe.set_user(self.shopper)
		wishlist.add_to_wishlist(self.product)
		frappe.set_user("Administrator")
		other_shopper = make_website_user()
		frappe.set_user(other_shopper)

		self.assertEqual(wishlist.get_wishlist()["count"], 0)
		wishlist.remove_from_wishlist(self.product)

		self.assertTrue(frappe.db.exists("Commera Wishlist Item", {"user": self.shopper}))
