# Copyright (c) 2026, company@bwhstudios.com and contributors
# See license.txt

"""The /og-image endpoint (www/og_image_render.py): cache files, the render lock and the failure cache."""

import glob
import os
from unittest.mock import call, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_files_path

from commera import branding
from commera.og import generator
from commera.og.test_generator import get_published_variant
from commera.tests import get_test_configurator, get_test_item
from commera.www import og_image_render

JPEG = b"\xff\xd8\xff-card"


class OgServingTestCase(IntegrationTestCase):
	def setUp(self):
		self.cache_dir = os.path.join(get_files_path(is_private=False), og_image_render.CACHE_SUBDIR)
		os.makedirs(self.cache_dir, exist_ok=True)
		self.cache_path = os.path.join(self.cache_dir, f"ogtest{frappe.generate_hash(length=10)}-1.jpg")
		self.addCleanup(self.forget_card, self.cache_path)
		self.addCleanup(setattr, frappe.local.flags, "redirect_location", None)
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)

	def forget_card(self, path):
		name = os.path.basename(path)
		frappe.cache.delete_value([f"commera_og_failed:{name}", f"commera_og_lock:{name.split('-', 1)[0]}"])
		if os.path.exists(path):
			os.remove(path)

	def request(self, route, **params):
		frappe.local.form_dict = frappe._dict(route=route, **params)
		return og_image_render.get_context(frappe._dict())

	def published_route(self):
		variant = get_published_variant()
		if not variant:
			self.skipTest("No published Style Attribute Variant available.")
		return variant.route

	def pin_cache_path(self):
		return patch.object(og_image_render, "cache_file_path", return_value=self.cache_path)


class TestServeOgImage(OgServingTestCase):
	def test_an_unknown_route_is_not_found(self):
		with self.assertRaises(frappe.DoesNotExistError):
			og_image_render.serve_og_image(f"no-such-route-{frappe.generate_hash(length=10)}")

	def test_an_unpublished_variant_is_not_found(self):
		route = f"og-test-draft-{frappe.generate_hash(length=10)}"
		variant = frappe.new_doc("Style Attribute Variant")
		variant.configurator = get_test_configurator()
		variant.item_style = get_test_item()
		variant.attribute_value = f"Val {frappe.generate_hash(length=6)}"
		variant.display_name = f"Draft {route}"
		variant.route = route
		variant.is_published = 0
		variant.insert(ignore_permissions=True)

		with self.assertRaises(frappe.DoesNotExistError):
			og_image_render.serve_og_image(route)

	def test_renders_once_writes_the_cache_and_redirects_to_it(self):
		route = self.published_route()
		with (
			patch.object(og_image_render, "render_card_for_doc", return_value=JPEG) as render,
			self.pin_cache_path(),
		):
			for _attempt in range(2):
				with self.assertRaises(frappe.Redirect) as redirect:
					self.request(f"{route}.jpg")

		render.assert_called_once()
		self.assertEqual(redirect.exception.http_status_code, 302)
		with open(self.cache_path, "rb") as cache_file:
			self.assertEqual(cache_file.read(), JPEG)
		self.assertEqual(
			frappe.local.flags.redirect_location,
			f"/files/{og_image_render.CACHE_SUBDIR}/{os.path.basename(self.cache_path)}",
		)
		self.assertEqual(glob.glob(f"{self.cache_path}.tmp-*"), [])

	def test_an_old_png_url_redirects_to_the_jpg_card(self):
		with self.assertRaises(frappe.Redirect) as redirect:
			self.request("brake-pads.png")
		self.assertEqual(redirect.exception.http_status_code, 301)
		self.assertEqual(frappe.local.flags.redirect_location, "/og-image/brake-pads.jpg")

		with self.assertRaises(frappe.Redirect):
			self.request("store.png")
		self.assertEqual(frappe.local.flags.redirect_location, "/og-image/store.jpg")

		with self.assertRaises(frappe.Redirect):
			self.request("brake-pads.png", price="none")
		self.assertEqual(frappe.local.flags.redirect_location, "/og-image/brake-pads.jpg?price=none")

	def test_a_new_card_version_removes_the_older_files_of_that_card_only(self):
		route = self.published_route()
		doc = frappe.get_cached_doc("Style Attribute Variant", {"route": route})
		older = og_image_render.cache_file_path(route, "an older version")
		other_card = og_image_render.cache_file_path(f"{route}?price=none", "an older version")
		current = og_image_render.cache_file_path(route, generator.get_variant_card_version(doc))
		for path in (older, other_card, current):
			self.addCleanup(self.forget_card, path)
		for path in (older, other_card):
			og_image_render.write_cache(path, b"old")

		with patch.object(og_image_render, "render_card_for_doc", return_value=JPEG):
			with self.assertRaises(frappe.Redirect):
				og_image_render.serve_og_image(route)

		self.assertTrue(os.path.exists(current))
		self.assertFalse(os.path.exists(older))
		self.assertTrue(os.path.exists(other_card))

	def test_old_request_snapshot_cannot_remove_a_card_published_before_its_lock(self):
		newer = self.cache_path.replace("-1.jpg", "-2.jpg")
		self.addCleanup(self.forget_card, newer)
		old_doc = frappe._dict(name="og-snapshot", modified="old", is_published=1)
		new_doc = frappe._dict(name="og-snapshot", modified="new", is_published=1)
		acquire = frappe.cache.set

		def publish_before_lock(*args, **kwargs):
			og_image_render.write_cache(newer, JPEG)
			return acquire(*args, **kwargs)

		def read_doc(*args, **kwargs):
			# Ordinary reads retain the old snapshot; locking reads see the committed update.
			return new_doc if kwargs.get("for_update") else old_doc

		with (
			patch.object(frappe.db, "get_value", return_value=old_doc),
			patch("frappe.get_cached_doc", return_value=old_doc),
			patch("frappe.get_doc", side_effect=read_doc),
			patch.object(og_image_render, "get_variant_card_version", side_effect=lambda doc: doc.modified),
			patch.object(
				og_image_render,
				"cache_file_path",
				side_effect=lambda card, version: newer if version == "new" else self.cache_path,
			),
			patch("frappe.cache.set", side_effect=publish_before_lock),
			patch.object(og_image_render, "render_card_for_doc", return_value=JPEG),
			self.assertRaises(og_image_render.CardBusy),
		):
			og_image_render.serve_og_image("og-snapshot")

		self.assertTrue(os.path.exists(newer))
		self.assertFalse(os.path.exists(self.cache_path))

	def test_a_renderer_upgrade_ignores_old_cards(self):
		with patch.object(og_image_render, "RENDERER_VERSION", 2):
			old = og_image_render.cache_file_path("some-route", "v1")
		self.assertNotEqual(old, og_image_render.cache_file_path("some-route", "v1"))
		self.assertEqual(
			os.path.basename(old).split("-")[0],
			os.path.basename(og_image_render.cache_file_path("some-route", "v1")).split("-")[0],
		)

	def test_the_cache_key_is_deterministic(self):
		first = og_image_render.cache_file_path("some-route", "2026-06-17 14:08:55.980572")
		self.assertEqual(first, og_image_render.cache_file_path("some-route", "2026-06-17 14:08:55.980572"))
		self.assertNotEqual(first, og_image_render.cache_file_path("some-route", "2026-06-18 00:00:00"))
		self.assertTrue(first.endswith(".jpg"))


class TestRenderLock(OgServingTestCase):
	def test_a_second_request_during_a_render_gets_a_503_and_starts_no_render(self):
		route = self.published_route()
		renders = []

		def render(*args, **kwargs):
			renders.append(args)
			with self.assertRaises(og_image_render.CardBusy) as busy:
				self.request(f"{route}.jpg")
			self.assertEqual(busy.exception.http_status_code, 503)
			self.assertEqual(frappe.local.response_headers.get("Retry-After"), "10")
			return JPEG

		with (
			patch.object(og_image_render, "render_card_for_doc", side_effect=render),
			self.pin_cache_path(),
			self.assertRaises(frappe.Redirect),
		):
			self.request(f"{route}.jpg")

		self.assertEqual(len(renders), 1)

	def test_the_lock_is_released_after_a_render(self):
		calls = []
		og_image_render.render_once(self.cache_path, lambda: calls.append(1) or JPEG)
		os.remove(self.cache_path)
		og_image_render.render_once(self.cache_path, lambda: calls.append(1) or JPEG)
		self.assertEqual(len(calls), 2)

	def test_expired_holder_cannot_delete_successor_lock_or_write(self):
		key = frappe.cache.make_key(f"commera_og_lock:{os.path.basename(self.cache_path).split('-', 1)[0]}")

		def render():
			# Simulate expiry and a successor acquiring the stable card lock.
			# The key is site-prefixed; simulate the raw Redis lock, not a pickled cache value.
			# nosemgrep: frappe-semgrep-rules.rules.frappe-cache-breaks-multitenancy
			frappe.cache.set(key, "successor", ex=300)
			return JPEG

		with self.assertRaises(og_image_render.CardBusy):
			og_image_render.render_once(self.cache_path, render)
		self.assertTrue(og_image_render.owns_lock(key, "successor"))
		self.assertFalse(os.path.exists(self.cache_path))
		og_image_render.release_lock(key, "successor")

	def test_different_fingerprints_share_one_lock(self):
		newer = self.cache_path.replace("-1.jpg", "-2.jpg")
		self.addCleanup(self.forget_card, newer)

		def render():
			with self.assertRaises(og_image_render.CardBusy):
				og_image_render.render_once(newer, lambda: JPEG)
			return JPEG

		og_image_render.render_once(self.cache_path, render)

	def test_stale_render_does_not_write_or_remove_current_card(self):
		newer = self.cache_path.replace("-1.jpg", "-2.jpg")
		self.addCleanup(self.forget_card, newer)
		og_image_render.write_cache(newer, JPEG)
		with self.assertRaises(og_image_render.CardBusy):
			og_image_render.render_once(self.cache_path, lambda: JPEG, lambda: newer)
		self.assertTrue(os.path.exists(newer))
		self.assertFalse(os.path.exists(self.cache_path))

	def test_a_failed_render_is_not_tried_again_for_ten_minutes(self):
		route = self.published_route()
		with (
			patch.object(
				og_image_render, "render_card_for_doc", side_effect=RuntimeError("no chromium")
			) as render,
			patch.object(og_image_render, "product_photo_url", return_value="/files/photo.jpg"),
			patch("frappe.cache.set_value", wraps=frappe.cache.set_value) as set_value,
			self.pin_cache_path(),
		):
			for _attempt in range(3):
				with self.assertRaises(frappe.Redirect) as redirect:
					self.request(f"{route}.jpg")
				self.assertEqual(frappe.local.flags.redirect_location, "/files/photo.jpg")

		render.assert_called_once()
		self.assertEqual(redirect.exception.http_status_code, 302)
		failure_key = f"commera_og_failed:{os.path.basename(self.cache_path)}"
		self.assertIn(call(failure_key, 1, expires_in_sec=600), set_value.call_args_list)
		self.assertFalse(os.path.exists(self.cache_path))


class TestServeStoreCard(OgServingTestCase):
	def test_renders_once_then_serves_from_cache(self):
		with (
			patch.object(og_image_render, "render_card_image", return_value=JPEG) as render,
			self.pin_cache_path(),
		):
			for _attempt in range(2):
				with self.assertRaises(frappe.Redirect):
					self.request("store.jpg")

		render.assert_called_once()
		self.assertIn("<!doctype html>", render.call_args.args[0])
		self.assertTrue(frappe.local.flags.redirect_location.endswith(os.path.basename(self.cache_path)))

	def test_a_failed_render_falls_back_to_the_store_logo(self):
		with (
			patch.object(og_image_render, "render_card_image", side_effect=RuntimeError("no chromium")),
			self.pin_cache_path(),
			self.assertRaises(frappe.Redirect),
		):
			self.request("store.jpg")

		self.assertEqual(frappe.local.flags.redirect_location, branding.get_brand_assets().logo)
