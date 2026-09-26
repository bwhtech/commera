# Copyright (c) 2026, company@bwhstudios.com and contributors
# See license.txt

"""Tests for the Satori OG-image render core (og/generator.py) and the /og-image web layer."""

import base64
import os
import time
import unittest
from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, get_files_path

from commera import branding, seo
from commera.og import generator
from commera.tests import get_test_configurator, get_test_item
from commera.www import og_image_render


def get_published_variant():
	rows = frappe.get_all("Style Attribute Variant", {"is_published": 1}, ["name", "route"], limit=1)
	return rows[0] if rows else None


class TestResolveTemplate(IntegrationTestCase):
	def test_returns_bundled_path_when_no_enabled_template(self):
		# A DocType with no OG Image Template row must fall back to the bundled path.
		frappe.db.delete("OG Image Template", {"for_doctype": "Style Attribute Variant"})
		result = generator.resolve_template("Style Attribute Variant")
		self.assertEqual(result, generator.BUNDLED_CARD_TEMPLATE)

	def test_returns_admin_template_html_when_enabled_row_exists(self):
		marker = f"<div>custom-{frappe.generate_hash(length=8)}</div>"
		frappe.db.delete("OG Image Template", {"for_doctype": "Style Attribute Variant"})
		template = frappe.get_doc(
			{
				"doctype": "OG Image Template",
				"for_doctype": "Style Attribute Variant",
				"enabled": 1,
				"template_html": marker,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "OG Image Template", template.name, force=True)

		result = generator.resolve_template("Style Attribute Variant")
		self.assertEqual(result, marker)

	def test_disabled_template_is_ignored(self):
		frappe.db.delete("OG Image Template", {"for_doctype": "Style Attribute Variant"})
		template = frappe.get_doc(
			{
				"doctype": "OG Image Template",
				"for_doctype": "Style Attribute Variant",
				"enabled": 0,
				"template_html": "<div>disabled</div>",
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "OG Image Template", template.name, force=True)

		result = generator.resolve_template("Style Attribute Variant")
		self.assertEqual(result, generator.BUNDLED_CARD_TEMPLATE)


class TestProductImageDataUri(IntegrationTestCase):
	def test_returns_none_for_http_url(self):
		self.assertIsNone(generator.product_image_data_uri("http://example.com/a.png"))

	def test_returns_none_for_https_url(self):
		self.assertIsNone(generator.product_image_data_uri("https://example.com/a.png"))

	def test_returns_none_for_missing_files_path(self):
		missing = f"/files/og-test-missing-{frappe.generate_hash(length=10)}.png"
		self.assertIsNone(generator.product_image_data_uri(missing))

	def test_returns_none_for_non_files_path(self):
		self.assertIsNone(generator.product_image_data_uri("/assets/something.png"))

	def test_returns_jpeg_data_uri_and_downscales_large_source(self):
		from PIL import Image

		# Write a large opaque PNG to public files; far bigger than CARD_PHOTO_PX.
		filename = f"og-test-src-{frappe.generate_hash(length=10)}.png"
		public_path = os.path.join(get_files_path(is_private=False), filename)
		large = Image.new("RGB", (1600, 1600), (10, 20, 30))
		large.save(public_path, format="PNG")
		self.addCleanup(lambda: os.path.exists(public_path) and os.remove(public_path))

		source_bytes = os.path.getsize(public_path)
		data_uri = generator.product_image_data_uri(f"/files/{filename}")

		self.assertIsNotNone(data_uri)
		self.assertTrue(data_uri.startswith("data:image/jpeg;base64,"))

		decoded = base64.b64decode(data_uri[len("data:image/jpeg;base64,") :])
		# Downscale sanity: the inlined JPEG is meaningfully smaller than the source.
		self.assertLess(len(decoded), source_bytes)

		# The longest edge must be clamped to CARD_PHOTO_PX.
		out_image = Image.open(BytesIO(decoded))
		self.assertEqual(out_image.format, "JPEG")
		self.assertLessEqual(max(out_image.size), generator.CARD_PHOTO_PX)

	def test_flattens_transparency_to_jpeg(self):
		from PIL import Image

		filename = f"og-test-rgba-{frappe.generate_hash(length=10)}.png"
		public_path = os.path.join(get_files_path(is_private=False), filename)
		rgba = Image.new("RGBA", (300, 300), (200, 0, 0, 0))  # fully transparent red
		rgba.save(public_path, format="PNG")
		self.addCleanup(lambda: os.path.exists(public_path) and os.remove(public_path))

		data_uri = generator.product_image_data_uri(f"/files/{filename}")
		self.assertIsNotNone(data_uri)
		self.assertTrue(data_uri.startswith("data:image/jpeg;base64,"))
		decoded = base64.b64decode(data_uri[len("data:image/jpeg;base64,") :])
		out_image = Image.open(BytesIO(decoded))
		self.assertEqual(out_image.mode, "RGB")  # alpha flattened away


class TestContextBuilderFor(IntegrationTestCase):
	def test_returns_builder_for_style_attribute_variant(self):
		builder = generator.context_builder_for("Style Attribute Variant")
		self.assertIs(builder, generator.build_variant_card_context)

	def test_raises_for_unregistered_doctype(self):
		with self.assertRaises(frappe.ValidationError):
			generator.context_builder_for("User")


class TestPriceParity(IntegrationTestCase):
	def setUp(self):
		self.variant = get_published_variant()
		if not self.variant:
			self.skipTest("No published Style Attribute Variant available to test price parity.")

	def test_card_price_matches_product_detail_source(self):
		from commera.product_detail import get_product_detail

		variant_doc = frappe.get_doc("Style Attribute Variant", self.variant.name)
		detail = get_product_detail(self.variant.route)

		context = generator.build_variant_card_context(variant_doc)

		amount = (detail or {}).get("sale_price") or (detail or {}).get("default_price")
		if amount:
			expected = f"{seo.get_site_currency()} {flt(amount):.2f}"
		else:
			expected = ""
		self.assertEqual(context["price"], expected)

	def test_context_shape(self):
		variant_doc = frappe.get_doc("Style Attribute Variant", self.variant.name)
		context = generator.build_variant_card_context(variant_doc)
		for key in ("store_name", "display_name", "brand", "price", "photo_data_uri", "doc"):
			self.assertIn(key, context)
		self.assertIs(context["doc"], variant_doc)
		self.assertEqual(context["store_name"], seo.get_store_name())


class TestServeOgImage(IntegrationTestCase):
	def setUp(self):
		frappe.local.flags.redirect_location = None

	def tearDown(self):
		frappe.local.flags.redirect_location = None

	def test_raises_does_not_exist_for_unknown_route(self):
		unknown = f"no-such-route-{frappe.generate_hash(length=10)}"
		with self.assertRaises(frappe.DoesNotExistError):
			og_image_render.serve_og_image(unknown)

	def test_raises_does_not_exist_for_unpublished_variant(self):
		# A draft route must 404 rather than leak an unreleased product card to a crawler.
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

	def test_redirects_and_writes_cache_on_success(self):
		variant = get_published_variant()
		if not variant:
			self.skipTest("No published Style Attribute Variant available.")

		# Pin the cache path so the render -> write -> redirect contract runs in isolation from disk state.
		public_root = get_files_path(is_private=False)
		cache_dir = os.path.join(public_root, og_image_render.CACHE_SUBDIR)
		os.makedirs(cache_dir, exist_ok=True)
		cache_path = os.path.join(cache_dir, f"og-test-{frappe.generate_hash(length=12)}.png")
		if os.path.exists(cache_path):
			os.remove(cache_path)
		self.addCleanup(lambda: os.path.exists(cache_path) and os.remove(cache_path))

		fixed_png = b"\x89PNG\r\n\x1a\n-fake-card-bytes"
		# Mock ONLY the Node/Satori boundary; everything else is real.
		with (
			patch(
				"commera.www.og_image_render.render_card_for_doc",
				return_value=fixed_png,
			) as mocked,
			patch(
				"commera.www.og_image_render.cache_file_path",
				return_value=cache_path,
			),
		):
			with self.assertRaises(frappe.Redirect):
				og_image_render.serve_og_image(variant.route)

		mocked.assert_called_once()
		self.assertTrue(os.path.exists(cache_path))
		with open(cache_path, "rb") as cache_file:
			self.assertEqual(cache_file.read(), fixed_png)

		expected_url = "/files/" + os.path.relpath(cache_path, public_root).replace(os.sep, "/")
		self.assertEqual(frappe.local.flags.redirect_location, expected_url)

	def test_cached_card_is_served_without_rerender(self):
		variant = get_published_variant()
		if not variant:
			self.skipTest("No published Style Attribute Variant available.")

		public_root = get_files_path(is_private=False)
		cache_dir = os.path.join(public_root, og_image_render.CACHE_SUBDIR)
		os.makedirs(cache_dir, exist_ok=True)
		cache_path = os.path.join(cache_dir, f"og-test-{frappe.generate_hash(length=12)}.png")
		og_image_render.write_cache(cache_path, b"cached")
		self.addCleanup(lambda: os.path.exists(cache_path) and os.remove(cache_path))

		# Pin the same path on both calls so the cache-hit branch is reachable.
		with (
			patch("commera.www.og_image_render.render_card_for_doc") as mocked,
			patch(
				"commera.www.og_image_render.cache_file_path",
				return_value=cache_path,
			),
		):
			with self.assertRaises(frappe.Redirect):
				og_image_render.serve_og_image(variant.route)
			mocked.assert_not_called()

	def test_cache_key_is_deterministic(self):
		"""Cache key must be stable per (route, modified): frappe.generate_hash ignores its input in v15."""
		route = "some-route"
		modified = "2026-06-17 14:08:55.980572"
		first = og_image_render.cache_file_path(route, modified)
		second = og_image_render.cache_file_path(route, modified)
		self.assertEqual(first, second)
		# A different modified timestamp must yield a different key (auto-invalidation).
		self.assertNotEqual(first, og_image_render.cache_file_path(route, "2026-06-18 00:00:00"))


class TestStoreCard(IntegrationTestCase):
	def setUp(self):
		frappe.local.flags.redirect_location = None
		public_root = get_files_path(is_private=False)
		cache_dir = os.path.join(public_root, og_image_render.CACHE_SUBDIR)
		os.makedirs(cache_dir, exist_ok=True)
		self.cache_path = os.path.join(cache_dir, f"og-test-{frappe.generate_hash(length=12)}.png")
		self.addCleanup(lambda: os.path.exists(self.cache_path) and os.remove(self.cache_path))
		self.expected_url = "/files/" + os.path.relpath(self.cache_path, public_root).replace(os.sep, "/")

	def tearDown(self):
		frappe.local.flags.redirect_location = None

	def test_card_carries_the_store_name_and_inlined_logo(self):
		html_str = generator.build_store_card_html()

		self.assertIn(seo.get_store_name(), html_str)
		self.assertIn("data:image/", html_str)

	def test_bundled_svg_logo_is_inlined_as_svg(self):
		self.assertTrue(
			generator.logo_data_uri(branding.BUNDLED_LOGO).startswith("data:image/svg+xml;base64,")
		)

	def test_raster_logo_keeps_its_transparency(self):
		from PIL import Image

		buffer = BytesIO()
		Image.new("RGBA", (40, 20), (0, 0, 0, 0)).save(buffer, format="PNG")
		logo = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"og-logo-{frappe.generate_hash(length=8)}.png",
				"content": buffer.getvalue(),
				"is_private": 0,
			}
		).insert(ignore_permissions=True)

		data_uri = generator.logo_data_uri(logo.file_url)

		self.assertTrue(data_uri.startswith("data:image/png;base64,"))
		inlined = Image.open(BytesIO(base64.b64decode(data_uri.split(",", 1)[1])))
		self.assertEqual(inlined.getpixel((0, 0))[3], 0)

	def test_remote_logo_is_skipped(self):
		self.assertIsNone(generator.logo_data_uri("https://cdn.example.com/logo.png"))

	def test_renders_once_then_serves_from_cache(self):
		fixed_png = b"\x89PNG\r\n\x1a\n-fake-store-card"
		# Mock ONLY the Node/Satori boundary; the template and the cache are real.
		with (
			patch("commera.www.og_image_render.render_og_png", return_value=fixed_png) as mocked,
			patch("commera.www.og_image_render.cache_file_path", return_value=self.cache_path),
		):
			for _attempt in range(2):
				with self.assertRaises(frappe.Redirect):
					og_image_render.serve_store_card()

		mocked.assert_called_once()
		with open(self.cache_path, "rb") as cache_file:
			self.assertEqual(cache_file.read(), fixed_png)
		self.assertEqual(frappe.local.flags.redirect_location, self.expected_url)

	def test_failed_render_falls_back_to_the_store_logo(self):
		frappe.form_dict.route = "store.png"
		self.addCleanup(frappe.form_dict.pop, "route", None)

		with (
			patch("commera.www.og_image_render.render_og_png", side_effect=RuntimeError("node missing")),
			patch("commera.www.og_image_render.cache_file_path", return_value=self.cache_path),
		):
			with self.assertRaises(frappe.Redirect):
				og_image_render.get_context(frappe._dict())

		self.assertEqual(frappe.local.flags.redirect_location, branding.get_brand_assets().logo)


class TestClearOldCards(IntegrationTestCase):
	"""The cache key embeds `modified`, so every edit strands a PNG; clear_old_cards is the only bound."""

	def setUp(self):
		self.cache_dir = os.path.join(get_files_path(is_private=False), "og-cache")
		os.makedirs(self.cache_dir, exist_ok=True)

	def write_card(self, age_days, suffix=".png"):
		path = os.path.join(self.cache_dir, f"og-test-{frappe.generate_hash(length=12)}{suffix}")
		with open(path, "wb") as card_file:
			card_file.write(b"\x89PNG\r\n\x1a\n")
		aged = time.time() - (age_days * 86400)
		os.utime(path, (aged, aged))
		self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
		return path

	def test_stale_card_is_pruned_and_fresh_one_survives(self):
		stale = self.write_card(age_days=45)
		fresh = self.write_card(age_days=1)

		generator.clear_old_cards(days=30)

		self.assertFalse(os.path.exists(stale))
		self.assertTrue(os.path.exists(fresh))

	def test_cutoff_is_the_days_argument_not_the_default(self):
		# 10 days old: pruned at days=5, kept at the 30-day default.
		card = self.write_card(age_days=10)
		generator.clear_old_cards(days=30)
		self.assertTrue(os.path.exists(card))
		generator.clear_old_cards(days=5)
		self.assertFalse(os.path.exists(card))

	def test_non_png_files_are_left_alone(self):
		# The cache dir sits under public/files; only our own .png cards may be deleted.
		bystander = self.write_card(age_days=365, suffix=".txt")
		generator.clear_old_cards(days=30)
		self.assertTrue(os.path.exists(bystander))

	def test_missing_cache_dir_is_a_no_op(self):
		with patch(
			"commera.og.generator.get_files_path",
			return_value=os.path.join(self.cache_dir, f"nope-{frappe.generate_hash(length=8)}"),
		):
			generator.clear_old_cards(days=30)  # must not raise


class TestRenderOgPng(IntegrationTestCase):
	"""End-to-end through the real Node/Satori subprocess - the only cover for og_satori.mjs, fonts and resvg."""

	def test_renders_a_spec_sized_png(self):
		from PIL import Image

		html_str = "<div style='display:flex;width:100%;height:100%;background:#fff'>OG</div>"
		png_bytes = generator.render_og_png(html_str, generator.DEFAULT_OG_WIDTH, generator.DEFAULT_OG_HEIGHT)

		image = Image.open(BytesIO(png_bytes))
		self.assertEqual(image.format, "PNG")
		self.assertEqual(image.size, (generator.DEFAULT_OG_WIDTH, generator.DEFAULT_OG_HEIGHT))

	def test_store_card_renders_a_spec_sized_png(self):
		from PIL import Image

		png_bytes = generator.render_og_png(
			generator.build_store_card_html(), generator.DEFAULT_OG_WIDTH, generator.DEFAULT_OG_HEIGHT
		)

		image = Image.open(BytesIO(png_bytes))
		self.assertEqual(image.size, (generator.DEFAULT_OG_WIDTH, generator.DEFAULT_OG_HEIGHT))

	def test_render_card_for_doc_produces_a_png_for_a_real_variant(self):
		from PIL import Image

		variant = get_published_variant()
		if not variant:
			self.skipTest("No published Style Attribute Variant available.")

		variant_doc = frappe.get_doc("Style Attribute Variant", variant.name)
		png_bytes = generator.render_card_for_doc("Style Attribute Variant", variant_doc)

		image = Image.open(BytesIO(png_bytes))
		self.assertEqual(image.size, (generator.DEFAULT_OG_WIDTH, generator.DEFAULT_OG_HEIGHT))
