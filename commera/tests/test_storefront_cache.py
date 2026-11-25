import frappe
from frappe.tests import UnitTestCase

from commera import storefront_cache as sfc


class TestStorefrontCache(UnitTestCase):
	def setUp(self):
		super().setUp()
		frappe.flags.enable_storefront_cache_in_test = True
		sfc.clear_all_storefront_caches()

	def tearDown(self):
		frappe.flags.enable_storefront_cache_in_test = False
		sfc.clear_all_storefront_caches()
		super().tearDown()

	def test_epoch_bump_invalidates_matching_domain_only(self):
		catalog_calls = 0
		shop_calls = 0

		def compute_catalog():
			nonlocal catalog_calls
			catalog_calls += 1
			return {"v": catalog_calls}

		def compute_shop():
			nonlocal shop_calls
			shop_calls += 1
			return {"v": shop_calls}

		self.assertEqual(
			sfc.get_or_compute("test.cat", ("a",), ("catalog",), compute_catalog, include_locale=False),
			{"v": 1},
		)
		self.assertEqual(
			sfc.get_or_compute("test.cat", ("a",), ("catalog",), compute_catalog, include_locale=False),
			{"v": 1},
		)
		self.assertEqual(
			sfc.get_or_compute("test.shop", ("b",), ("shop",), compute_shop, include_locale=False),
			{"v": 1},
		)

		# Bump catalog epoch only: catalog recomputes, shop stays cached
		sfc.bump_catalog()
		self.assertEqual(
			sfc.get_or_compute("test.cat", ("a",), ("catalog",), compute_catalog, include_locale=False),
			{"v": 2},
		)
		self.assertEqual(
			sfc.get_or_compute("test.shop", ("b",), ("shop",), compute_shop, include_locale=False),
			{"v": 1},
		)

		# Bump shop epoch: shop recomputes
		sfc.bump_shop()
		self.assertEqual(
			sfc.get_or_compute("test.shop", ("b",), ("shop",), compute_shop, include_locale=False),
			{"v": 2},
		)

	def test_guest_only_gate_skips_cache_for_signed_in_users(self):
		calls = 0

		def compute():
			nonlocal calls
			calls += 1
			return {"calls": calls}

		frappe.set_user("Administrator")
		self.assertEqual(
			sfc.cached_guest_api("test.guest", ("k",), ("catalog",), compute, include_locale=False),
			{"calls": 1},
		)
		self.assertEqual(
			sfc.cached_guest_api("test.guest", ("k",), ("catalog",), compute, include_locale=False),
			{"calls": 2},
		)

		frappe.set_user("Guest")
		self.assertEqual(
			sfc.cached_guest_api("test.guest", ("k",), ("catalog",), compute, include_locale=False),
			{"calls": 3},
		)
		self.assertEqual(
			sfc.cached_guest_api("test.guest", ("k",), ("catalog",), compute, include_locale=False),
			{"calls": 3},
		)
		frappe.set_user("Administrator")

	def test_cart_and_checkout_caches_invalidate_on_revision_or_modified(self):
		cart_calls = 0

		def compute_cart():
			nonlocal cart_calls
			cart_calls += 1
			return {"rev_calls": cart_calls}

		self.assertEqual(sfc.cached_cart_response("CART-1", 1, "2026-01-01 00:00:00", compute_cart), {"rev_calls": 1})
		self.assertEqual(sfc.cached_cart_response("CART-1", 1, "2026-01-01 00:00:00", compute_cart), {"rev_calls": 1})
		# Cart revision incremented -> immediate cache miss
		self.assertEqual(sfc.cached_cart_response("CART-1", 2, "2026-01-01 00:00:01", compute_cart), {"rev_calls": 2})
		# Price epoch bumped -> immediate cache miss even at same revision
		sfc.bump_prices()
		self.assertEqual(sfc.cached_cart_response("CART-1", 2, "2026-01-01 00:00:01", compute_cart), {"rev_calls": 3})

		chk_calls = 0

		def compute_chk():
			nonlocal chk_calls
			chk_calls += 1
			return {"chk_calls": chk_calls}

		self.assertEqual(sfc.cached_checkout_response("QTN-1", "2026-01-01 00:00:00", compute_chk), {"chk_calls": 1})
		self.assertEqual(sfc.cached_checkout_response("QTN-1", "2026-01-01 00:00:00", compute_chk), {"chk_calls": 1})
		self.assertEqual(sfc.cached_checkout_response("QTN-1", "2026-01-01 00:00:05", compute_chk), {"chk_calls": 2})
		sfc.bump_shop()
		self.assertEqual(sfc.cached_checkout_response("QTN-1", "2026-01-01 00:00:05", compute_chk), {"chk_calls": 3})
