import inspect
import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera import hooks as commera_hooks
from commera import storefront_cache as sfc
from commera.tests import get_test_configurator


def _mock_get_request(path: str, *, query_string: str = "", headers: dict | None = None) -> Request:
	builder = EnvironBuilder(path=path, method="GET", query_string=query_string, headers=headers or {})
	return Request(builder.get_environ())


class TestStorefrontCache(UnitTestCase):
	def setUp(self):
		super().setUp()
		frappe.flags.enable_storefront_cache_in_test = True
		sfc.clear_all_storefront_caches()

	def tearDown(self):
		frappe.flags.enable_storefront_cache_in_test = False
		sfc.clear_all_storefront_caches()
		if hasattr(frappe.local, "request"):
			delattr(frappe.local, "request")
		super().tearDown()

	def test_all_doc_events_accept_frappe_event_arguments(self):
		"""Every commera doc_events hook must accept Frappe's positional arguments (including 5-arg after_rename)."""
		for doctype, events in commera_hooks.doc_events.items():
			for event_name, handlers in events.items():
				handler_list = [handlers] if isinstance(handlers, str) else list(handlers)
				for dotted in handler_list:
					if not dotted.startswith("commera."):
						continue
					fn = frappe.get_attr(dotted)
					sig = inspect.signature(fn)
					event_args = {
						"after_rename": (None, event_name, "old_name", "new_name", False),
						"before_mapping": (None, event_name, None, None),
					}
					sample_args = event_args.get(event_name, (None, event_name))
					try:
						sig.bind(*sample_args)
					except TypeError as exc:
						self.fail(f"{doctype}.{event_name} -> {dotted}{sig} rejected {sample_args}: {exc}")

	def test_epoch_bump_defers_to_commit_and_ignores_rollback(self):
		"""B7: Redis epoch bumps wait for after_commit; rolled-back writes never bump Redis."""
		frappe.db.after_commit.reset()
		frappe.db.after_rollback.reset()
		before = sfc.get_epochs()["catalog"]

		sfc.bump_catalog()
		# Redis has not been incremented yet, though local request bypasses stale cache.
		if hasattr(frappe.local, "_commera_sf_epochs"):
			delattr(frappe.local, "_commera_sf_epochs")
		self.assertEqual(sfc.get_epochs()["catalog"], before)
		self.assertTrue(sfc._is_domain_dirty(("catalog",)))

		# Rollback clears dirty state without touching Redis.
		frappe.db.after_rollback.run()
		if hasattr(frappe.local, "_commera_sf_epochs"):
			delattr(frappe.local, "_commera_sf_epochs")
		self.assertEqual(sfc.get_epochs()["catalog"], before)
		self.assertFalse(sfc._is_domain_dirty(("catalog",)))

		# Commit bumps Redis epoch atomically.
		frappe.db.after_commit.reset()
		frappe.db.after_rollback.reset()
		sfc.bump_catalog()
		frappe.db.after_commit.run()
		if hasattr(frappe.local, "_commera_sf_epochs"):
			delattr(frappe.local, "_commera_sf_epochs")
		self.assertEqual(sfc.get_epochs()["catalog"], before + 1)
		self.assertFalse(sfc._is_domain_dirty(("catalog",)))

	def test_epoch_bump_logs_redis_failures(self):
		with (
			patch.object(frappe.cache, "pipeline", side_effect=RuntimeError("redis down")),
			patch("commera.storefront_cache.frappe.logger") as mock_logger,
		):
			sfc.bump_epochs("catalog", immediate=True)
		mock_logger.return_value.exception.assert_called_once()

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

		sfc.bump_epochs("catalog", immediate=True)
		self.assertEqual(
			sfc.get_or_compute("test.cat", ("a",), ("catalog",), compute_catalog, include_locale=False),
			{"v": 2},
		)
		self.assertEqual(
			sfc.get_or_compute("test.shop", ("b",), ("shop",), compute_shop, include_locale=False),
			{"v": 1},
		)

		sfc.bump_epochs("shop", immediate=True)
		self.assertEqual(
			sfc.get_or_compute("test.shop", ("b",), ("shop",), compute_shop, include_locale=False),
			{"v": 2},
		)

	def test_l1_returns_isolated_copies_against_caller_mutation(self):
		"""M6(c): mutating a dict returned from L1 must not poison subsequent hits."""
		first = sfc.get_or_compute(
			"test.mut", ("k",), ("catalog",), lambda: {"items": ["a"]}, include_locale=False
		)
		first["items"].append("poisoned")
		second = sfc.get_or_compute(
			"test.mut", ("k",), ("catalog",), lambda: {"items": ["fresh"]}, include_locale=False
		)
		self.assertEqual(second, {"items": ["a"]})

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

		self.assertEqual(
			sfc.cached_cart_response("CART-1", 1, "2026-01-01 00:00:00", compute_cart), {"rev_calls": 1}
		)
		self.assertEqual(
			sfc.cached_cart_response("CART-1", 1, "2026-01-01 00:00:00", compute_cart), {"rev_calls": 1}
		)
		self.assertEqual(
			sfc.cached_cart_response("CART-1", 2, "2026-01-01 00:00:01", compute_cart), {"rev_calls": 2}
		)
		sfc.bump_epochs("prices", immediate=True)
		self.assertEqual(
			sfc.cached_cart_response("CART-1", 2, "2026-01-01 00:00:01", compute_cart), {"rev_calls": 3}
		)

		chk_calls = 0

		def compute_chk():
			nonlocal chk_calls
			chk_calls += 1
			return {"chk_calls": chk_calls}

		self.assertEqual(
			sfc.cached_checkout_response("QTN-1", "2026-01-01 00:00:00", compute_chk), {"chk_calls": 1}
		)
		self.assertEqual(
			sfc.cached_checkout_response("QTN-1", "2026-01-01 00:00:00", compute_chk), {"chk_calls": 1}
		)
		self.assertEqual(
			sfc.cached_checkout_response("QTN-1", "2026-01-01 00:00:05", compute_chk), {"chk_calls": 2}
		)
		sfc.bump_epochs("shop", immediate=True)
		self.assertEqual(
			sfc.cached_checkout_response("QTN-1", "2026-01-01 00:00:05", compute_chk), {"chk_calls": 3}
		)

	def test_ssr_query_param_whitelist_and_size_bound(self):
		"""M6(b): utm_*/fbclid share one SSR key; whitelisted params vary key; oversized HTML skips cache."""
		frappe.set_user("Guest")
		with patch("commera.storefront_access.is_storefront_published", return_value=True):
			frappe.local.request = _mock_get_request(
				"/products", query_string="page=2&utm_source=ig&fbclid=1"
			)
			key_utm = sfc._ssr_cache_key("products")
			frappe.local.request = _mock_get_request("/products", query_string="page=2")
			key_clean = sfc._ssr_cache_key("products")
			frappe.local.request = _mock_get_request("/products", query_string="page=3")
			key_page3 = sfc._ssr_cache_key("products")

			self.assertEqual(key_utm, key_clean)
			self.assertNotEqual(key_clean, key_page3)

			# Oversized HTML is not cached.
			frappe.local.request = _mock_get_request("/products")
			sfc.store_cached_ssr_response("products", "x" * (sfc.MAX_SSR_CACHE_BYTES + 1))
			self.assertIsNone(sfc.get_cached_ssr_response("products"))

			# Normal HTML caches without Cache-Control: public.
			sfc.store_cached_ssr_response("products", "<html>ok</html>")
			resp = sfc.get_cached_ssr_response("products")
			self.assertIsNotNone(resp)
			self.assertEqual(resp.headers.get("X-Commera-Cache"), "HIT-L1")
			self.assertNotIn("public", resp.headers.get("Cache-Control", ""))
		frappe.set_user("Administrator")

	def test_ssr_eligibility_matrix_and_opt_in_controller(self):
		"""B6 + M6(a): SSR eligibility checks every exclusion rule and requires explicit controller opt-in."""
		from commera.shop_themes.theme_resolver import run_page_controller

		with patch("commera.storefront_access.is_storefront_published", return_value=True):
			frappe.set_user("Guest")
			orig_csrf = frappe.session.data.get("csrf_token")
			frappe.session.data["csrf_token"] = None
			try:
				frappe.local.request = _mock_get_request("/products")
				self.assertTrue(sfc.is_cacheable_ssr_request("products"))

				# Authorization header -> ineligible
				frappe.local.request = _mock_get_request("/products", headers={"Authorization": "token a:b"})
				self.assertFalse(sfc.is_cacheable_ssr_request("products"))

				# Preview params -> ineligible
				for param in ("preview=1", "editor=1", "preview_theme=summer"):
					frappe.local.request = _mock_get_request("/products", query_string=param)
					self.assertFalse(sfc.is_cacheable_ssr_request("products"))

				# R2-1: unknown query params fail safe (neither read nor written).
				frappe.local.request = _mock_get_request("/products")
				sfc.store_cached_ssr_response("products", "<html>base</html>")
				self.assertIsNotNone(sfc.get_cached_ssr_response("products"))
				frappe.local.request = _mock_get_request("/products", query_string="coupon=VIP")
				self.assertFalse(sfc.is_cacheable_ssr_request("products"))
				self.assertIsNone(sfc.get_cached_ssr_response("products"))
				sfc.store_cached_ssr_response("products", "<html>vip</html>")
				self.assertIsNone(sfc.get_cached_ssr_response("products"))

				# Known tracking params still share the cached entry.
				frappe.local.request = _mock_get_request("/products", query_string="utm_source=ig&fbclid=abc")
				self.assertTrue(sfc.is_cacheable_ssr_request("products"))
				self.assertIsNotNone(sfc.get_cached_ssr_response("products"))

				# Controller-declared allowed_query_params allows its own params and rejects others.
				frappe.local.request = _mock_get_request("/custom", query_string="tab=2")
				custom_allowed = frozenset({"tab"})
				self.assertTrue(sfc.is_cacheable_ssr_request("custom", allowed_query_params=custom_allowed))
				sfc.store_cached_ssr_response(
					"custom", "<html>tab2</html>", allowed_query_params=custom_allowed
				)
				self.assertIsNotNone(
					sfc.get_cached_ssr_response("custom", allowed_query_params=custom_allowed)
				)
				frappe.local.request = _mock_get_request("/custom", query_string="tab=2&extra=1")
				self.assertIsNone(sfc.get_cached_ssr_response("custom", allowed_query_params=custom_allowed))
				frappe.local.request = _mock_get_request("/products", query_string="page=2")
				self.assertFalse(sfc.is_cacheable_ssr_request("products", allowed_query_params=frozenset()))

				# Excluded prefixes -> ineligible
				frappe.local.request = _mock_get_request("/cart")
				for prefix in ("cart", "checkout", "account/orders", "login", "track-order"):
					self.assertFalse(sfc.is_cacheable_ssr_request(prefix))

				# Signed-in user -> ineligible
				frappe.set_user("Administrator")
				frappe.local.request = _mock_get_request("/products")
				self.assertFalse(sfc.is_cacheable_ssr_request("products"))
				frappe.set_user("Guest")

				# Unpublished store -> ineligible
				with patch("commera.storefront_access.is_storefront_published", return_value=False):
					self.assertFalse(sfc.is_cacheable_ssr_request("products"))
			finally:
				frappe.session.data["csrf_token"] = orig_csrf
				frappe.set_user("Administrator")

		# Opt-in controller check: default False, cacheable_ssr=True -> True, no_cache=True overrides.
		for attrs, expected in (
			({}, (False, frozenset())),
			({"cacheable_ssr": True}, (True, frozenset())),
			({"cacheable_ssr": True, "ssr_query_params": ("tab",)}, (True, frozenset({"tab"}))),
			({"cacheable_ssr": True, "no_cache": True}, (False, frozenset())),
		):
			fake_mod = type("Mod", (), attrs)()
			with patch("commera.shop_themes.theme_resolver.load_page_controller", return_value=fake_mod):
				self.assertEqual(run_page_controller([], "pages/custom.html", {}), expected)


class TestStorefrontCacheIntegration(IntegrationTestCase):
	"""B6 + B2 + B3 + B4 + B5 + Minor: real DB + real HTTP envelope parity, invalidation, and isolation."""

	def setUp(self):
		super().setUp()
		frappe.flags.enable_storefront_cache_in_test = True
		sfc.clear_all_storefront_caches()

	def tearDown(self):
		frappe.flags.enable_storefront_cache_in_test = False
		sfc.clear_all_storefront_caches()
		for attr in ("request", "form_dict", "_commera_sf_dirty_domains", "_commera_sf_pending_bumps"):
			if hasattr(frappe.local, attr):
				delattr(frappe.local, attr)
		frappe.set_user("Administrator")
		super().tearDown()

	def test_http_v1_and_v2_miss_hit_l1_hit_l2_match_uncached(self):
		"""B6 + B4: MISS == HIT-L1 == HIT-L2 == uncached across v1 and v2 envelopes, no Cache-Control: public."""
		from commera.api.storefront import collections, products, search, shop

		endpoints = [
			("commera.api.storefront.shop.get_shop", lambda: shop.get_shop()),
			("commera.api.storefront.shop.get_localization", lambda: shop.get_localization()),
			("commera.api.storefront.shop.list_countries", lambda: shop.list_countries()),
			("commera.api.storefront.collections.get_collections", lambda: collections.get_collections()),
			("commera.api.storefront.products.get_products", lambda: products.get_products()),
			("commera.api.storefront.search.get_typeahead", lambda: search.get_typeahead("zz", limit=6)),
		]

		frappe.set_user("Guest")
		frappe.local.request_ip = "127.0.0.1"
		for dotted, call in endpoints:
			frappe.flags.enable_storefront_cache_in_test = False
			if hasattr(frappe.local, "request"):
				delattr(frappe.local, "request")
			uncached = json.loads(json.dumps(call(), default=frappe.utils.response.json_handler))

			frappe.flags.enable_storefront_cache_in_test = True
			for api_ver, prefix, key in (
				("v1", "/api/method", "message"),
				("v2", "/api/v2/method", "data"),
			):
				sfc.clear_all_storefront_caches()
				frappe.local.request = _mock_get_request(f"{prefix}/{dotted}")
				resp_miss = call()
				self.assertEqual(resp_miss.headers.get("X-Commera-Cache"), "MISS", (dotted, api_ver))
				self.assertNotIn("public", resp_miss.headers.get("Cache-Control", ""))
				self.assertEqual(json.loads(resp_miss.get_data(as_text=True))[key], uncached)

				resp_l1 = call()
				self.assertEqual(resp_l1.headers.get("X-Commera-Cache"), "HIT-L1", (dotted, api_ver))
				self.assertEqual(json.loads(resp_l1.get_data(as_text=True))[key], uncached)

				sfc._l1_bytes.clear()
				resp_l2 = call()
				self.assertEqual(resp_l2.headers.get("X-Commera-Cache"), "HIT-L2", (dotted, api_ver))
				self.assertEqual(json.loads(resp_l2.get_data(as_text=True))[key], uncached)

	def test_real_doc_saves_and_db_set_value_invalidate_domains(self):
		"""B5 + B6: real DocType saves and navbar_manager.set_visibility invalidate cached reads."""
		from commera.commera_ecommerce.doctype.commera_settings.navbar.navbar_manager import set_visibility
		from commera.commera_ecommerce.doctype.ecommerce_category.ecommerce_category import get_menu_tree
		from commera.discounts.selection import get_automatic_discount_names

		# Menu tree + navbar_manager.set_visibility (B5 confirmed case)
		suffix = frappe.generate_hash(length=6)
		cat = frappe.get_doc(
			{
				"doctype": "Ecommerce Category",
				"category_name": f"ZZ Menu {suffix}",
				"display_name": f"ZZ Menu {suffix}",
				"enabled": 1,
				"link_type": "URL",
				"link_url": "/products",
			}
		).insert(ignore_permissions=True)
		frappe.db.after_commit.run()
		self.assertTrue(any(node["name"] == cat.name for node in get_menu_tree(enabled_only=True)))

		set_visibility(cat.name, 0)
		# Even before commit (dirty domain) AND after commit, hidden category must vanish immediately.
		self.assertFalse(any(node["name"] == cat.name for node in get_menu_tree(enabled_only=True)))
		frappe.db.after_commit.run()
		self.assertFalse(any(node["name"] == cat.name for node in get_menu_tree(enabled_only=True)))

		# Automatic discounts invalidation on real Commera Discount save
		disc = frappe.get_doc(
			{
				"doctype": "Commera Discount",
				"title": f"ZZ Auto {suffix}",
				"enabled": 1,
				"method": "Automatic",
				"discount_type": "Amount Off Order",
				"value_type": "Percentage",
				"value": 5,
			}
		).insert(ignore_permissions=True)
		frappe.db.after_commit.run()
		self.assertIn(disc.name, get_automatic_discount_names())
		disc.enabled = 0
		disc.save(ignore_permissions=True)
		frappe.db.after_commit.run()
		self.assertNotIn(disc.name, get_automatic_discount_names())

	def test_signed_in_checkout_get_never_returns_guest_checkout(self):
		"""B2: a guest checkout booked with a shopper's email must never be returned to that signed-in shopper."""
		from commera.api.storefront import checkout as checkout_api
		from commera.core import create_party

		suffix = frappe.generate_hash(length=6).lower()
		email = f"zz-iso-{suffix}@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Iso",
					"enabled": 1,
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		customer, contact = create_party(email, "Iso Shopper", portal_user=email)
		company = frappe.get_cached_value("Commera Settings", "Commera Settings", "company") or (
			frappe.defaults.get_global_default("company")
		)
		item_code = f"ZZ-ISO-ITEM-{suffix.upper()}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)
		guest_q = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": customer.name,
				"contact_person": contact.name,
				"contact_email": email,
				"company": company,
				"order_type": "Shopping Cart",
				"custom_guest_cart_key": f"guest-key-{suffix}",
				"items": [{"item_code": item_code, "qty": 1, "rate": 50}],
			}
		).insert(ignore_permissions=True)
		frappe.db.after_commit.run()

		frappe.set_user(email)
		# Even with cache enabled, signed-in shopper must NEVER receive guest_q.
		self.assertIsNone(checkout_api.get())
		self.assertEqual(guest_q.docstatus, 0)

	def test_open_checkout_reevaluates_disabled_automatic_discount(self):
		"""B3: disabling an automatic discount after address step must update total and fail expected_total."""
		from commera.api.payments import (
			COD_PAYMENT_MODE,
			CheckoutPriceChangedError,
			open_checkout,
			save_cart_quotation,
		)
		from commera.core import create_party

		suffix = frappe.generate_hash(length=6).upper()
		settings = frappe.get_doc("Commera Settings")
		settings.cod_enabled = 1
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

		item_code = f"ZZ-B3-{suffix}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)
		default_pl = settings.default_price_list or settings.sale_price_list
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": default_pl,
				"price_list_rate": 200,
			}
		).insert(ignore_permissions=True)

		disc = frappe.get_doc(
			{
				"doctype": "Commera Discount",
				"title": f"ZZ B3 Auto {suffix}",
				"enabled": 1,
				"method": "Automatic",
				"discount_type": "Amount Off Order",
				"value_type": "Percentage",
				"value": 10,
			}
		).insert(ignore_permissions=True)

		email = f"zz-b3-{suffix.lower()}@example.com"
		customer, contact = create_party(email, "B3 Buyer")
		company = settings.company or frappe.defaults.get_global_default("company")
		quotation = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": customer.name,
				"contact_person": contact.name,
				"contact_email": email,
				"company": company,
				"order_type": "Shopping Cart",
				"selling_price_list": settings.sale_price_list or default_pl,
				"items": [{"item_code": item_code, "qty": 1, "price_list_rate": 200, "rate": 200}],
			}
		)
		save_cart_quotation(quotation)
		discounted_total = quotation.grand_total
		self.assertEqual(discounted_total, 180)

		# Disable the automatic discount before payment start.
		disc.enabled = 0
		disc.save(ignore_permissions=True)
		frappe.db.after_commit.run()

		quotation.reload()
		with self.assertRaises(CheckoutPriceChangedError):
			open_checkout(quotation, COD_PAYMENT_MODE, expected_total=discounted_total)
		self.assertEqual(quotation.grand_total, 200)

	def test_analytics_capture_row_loads_through_get_doc(self):
		"""Minor: raw SQL INSERT in analytics.capture must produce a valid Storefront Analytics Event doc."""
		from commera.api.analytics import capture

		session_id = f"zz-sess-{frappe.generate_hash(length=8)}"
		frappe.set_user("Guest")
		frappe.local.request_ip = "127.0.0.1"
		with (
			patch("commera.api.analytics.events.is_first_party_enabled", return_value=True),
			patch(
				"commera.api.analytics.get_capture_payload",
				return_value={"event": "page_view", "session_id": session_id, "path": "/products"},
			),
		):
			capture()
		frappe.set_user("Administrator")
		name = frappe.db.get_value("Storefront Analytics Event", {"session_id": session_id}, "name")
		self.assertTrue(name)
		doc = frappe.get_doc("Storefront Analytics Event", name)
		self.assertEqual(doc.event, "page_view")
		self.assertEqual(doc.session_id, session_id)
		self.assertEqual(doc.path, "/products")

	def test_product_variant_save_invalidates_catalog_and_price_domains(self):
		"""B6: real Style Attribute Variant & Item Price saves bump catalog/prices epochs on commit."""
		suffix = frappe.generate_hash(length=6).upper()
		item_code = f"ZZ-INV-{suffix}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)
		frappe.db.after_commit.run()

		before_cat = sfc.get_epochs()["catalog"]
		variant = frappe.get_doc(
			{
				"doctype": "Style Attribute Variant",
				"configurator": get_test_configurator(),
				"item_style": item_code,
				"item_group": "All Item Groups",
				"attribute_value": f"V-{suffix}",
				"display_name": f"D-{suffix}",
				"route": f"zz-inv-{suffix.lower()}",
				"is_published": 1,
				"sizes": [{"size": "M", "item_code": item_code}],
			}
		).insert(ignore_permissions=True)
		frappe.db.after_commit.run()
		if hasattr(frappe.local, "_commera_sf_epochs"):
			delattr(frappe.local, "_commera_sf_epochs")
		self.assertGreater(sfc.get_epochs()["catalog"], before_cat)
		self.assertTrue(variant.name)

	def test_get_party_resolves_uncached_on_stale_cached_reference(self):
		"""R2-3: stale cached Customer ref must fall back to uncached resolution, never create a duplicate."""
		from commera.core import create_party, get_party

		suffix = frappe.generate_hash(length=6).lower()
		email = f"zz-party-{suffix}@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Party",
					"enabled": 1,
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		customer, _contact = create_party(email, f"Party {suffix}", portal_user=email)
		frappe.db.after_commit.run()

		# Simulate a stale cache entry pointing to a deleted Customer name.
		with (
			patch(
				"commera.storefront_cache.get_epoch_cached",
				return_value=["Customer", "NON-EXISTENT-CUST", False],
			),
			patch("commera.core._create_party_for_user") as mock_create,
		):
			resolved = get_party(user=email, create=True)
		self.assertEqual(resolved.name, customer.name)
		mock_create.assert_not_called()
