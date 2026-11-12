# Copyright (c) 2026, company@bwhstudios.com and contributors
# See license.txt

"""The OG card pages (og/generator.py), with Chromium stubbed: these tests read the HTML it gets."""

import os
import time
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, get_files_path
from markupsafe import escape

from commera import branding, seo
from commera.og import generator

CARD_FONTS = (
	"/assets/commera/fonts/OpenSans/OpenSans-Regular.ttf",
	"/assets/commera/fonts/OpenSans/OpenSans-Bold.ttf",
	"/assets/commera/fonts/IBMPlexSansArabic/IBMPlexSansArabic-Regular.ttf",
	"/assets/commera/fonts/IBMPlexSansArabic/IBMPlexSansArabic-Bold.ttf",
	"/assets/commera/fonts/IBMPlexSansHebrew/IBMPlexSansHebrew-Regular.ttf",
	"/assets/commera/fonts/IBMPlexSansHebrew/IBMPlexSansHebrew-Bold.ttf",
	"/assets/commera/fonts/NotoColorEmoji/Noto-COLRv1.woff2",
)
HOSTILE_TITLE = '"><img src=http://example.com/x>'


def get_published_variant():
	rows = frappe.get_all("Style Attribute Variant", {"is_published": 1}, ["name", "route"], limit=1)
	return rows[0] if rows else None


def make_public_file(test, name):
	path = os.path.join(get_files_path(is_private=False), name)
	with open(path, "wb") as image_file:
		image_file.write(b"\xff\xd8\xff")
	test.addCleanup(lambda: os.path.exists(path) and os.remove(path))
	return f"/files/{name}"


def use_og_template(test, template_html):
	frappe.db.delete("OG Image Template", {"for_doctype": "Style Attribute Variant"})
	template = frappe.get_doc(
		{
			"doctype": "OG Image Template",
			"for_doctype": "Style Attribute Variant",
			"enabled": 1,
			"template_html": template_html,
		}
	).insert(ignore_permissions=True)
	test.addCleanup(frappe.delete_doc, "OG Image Template", template.name, force=True)


class TestResolveTemplate(IntegrationTestCase):
	def test_returns_bundled_path_when_no_enabled_template(self):
		frappe.db.delete("OG Image Template", {"for_doctype": "Style Attribute Variant"})
		self.assertEqual(
			generator.resolve_template("Style Attribute Variant"), generator.BUNDLED_CARD_TEMPLATE
		)

	def test_returns_admin_template_html_when_enabled_row_exists(self):
		marker = f"<div>custom-{frappe.generate_hash(length=8)}</div>"
		use_og_template(self, marker)
		self.assertEqual(generator.resolve_template("Style Attribute Variant"), marker)

	def test_disabled_template_is_ignored(self):
		use_og_template(self, "<div>disabled</div>")
		frappe.db.set_value("OG Image Template", {"for_doctype": "Style Attribute Variant"}, "enabled", 0)
		self.assertEqual(
			generator.resolve_template("Style Attribute Variant"), generator.BUNDLED_CARD_TEMPLATE
		)


class TestCardImageUrl(IntegrationTestCase):
	def test_a_public_file_or_asset_is_kept(self):
		url = make_public_file(self, f"og-test-{frappe.generate_hash(length=10)}.jpg")
		self.assertEqual(generator.card_image_url(url), url)
		self.assertEqual(generator.card_image_url(branding.BUNDLED_LOGO), branding.BUNDLED_LOGO)

	def test_a_file_name_with_a_space_is_quoted(self):
		url = make_public_file(self, f"og test {frappe.generate_hash(length=10)}.jpg")
		self.assertEqual(generator.card_image_url(url), url.replace(" ", "%20"))
		self.assertEqual(generator.card_image_url(url.replace(" ", "%20")), url.replace(" ", "%20"))

	def test_remote_private_missing_and_climbing_images_are_dropped(self):
		public = make_public_file(self, f"og-test-{frappe.generate_hash(length=10)}.jpg")
		for url in (
			"http://example.com/a.png",
			"https://example.com/a.png",
			"//example.com/files/a.png",
			"/private/files/a.png",
			"/files/og-test-missing.png",
			"/assets/../site_config.json",
			"/files/../private/files/a.png",
			"/files/%2e%2e/private/files/a.png",
			f"/files/x/..{public.removeprefix('/files')}",
			"data:image/png;base64,AAAA",
			"",
			None,
		):
			with self.subTest(url=url):
				self.assertIsNone(generator.card_image_url(url))


class TestCardPage(IntegrationTestCase):
	"""What Chromium is asked to draw."""

	def render_product_card(self, **context):
		with patch.object(generator, "get_preview_from_html", return_value=b"jpg") as preview:
			html_str = generator.render_card_html(generator.BUNDLED_CARD_TEMPLATE, context)
			self.assertEqual(generator.render_card_image(html_str), b"jpg")
		return preview.call_args

	def test_the_card_is_a_1200_by_630_jpeg_with_a_content_policy_after_the_doctype(self):
		call = self.render_product_card(display_name="Brake pads")

		self.assertEqual(call.kwargs, {"format": "jpg", "width": 1200, "height": 630})
		html_str = call.args[0]
		self.assertTrue(html_str.startswith(f"<!doctype html>{generator.CONTENT_POLICY}"), html_str[:200])
		self.assertIn("default-src 'none'", generator.CONTENT_POLICY)

	def test_every_value_is_escaped(self):
		html_str = self.render_product_card(
			store_name=HOSTILE_TITLE, display_name=HOSTILE_TITLE, brand=HOSTILE_TITLE, price=HOSTILE_TITLE
		).args[0]

		self.assertNotIn("<img src=http://example.com", html_str)
		self.assertEqual(html_str.count("&#34;&gt;&lt;img src=http://example.com/x&gt;"), 4)

	def test_an_image_attribute_cannot_be_broken_out_of(self):
		html_str = self.render_product_card(photo_url='/files/a.jpg" onerror="x').args[0]
		self.assertIn('src="/files/a.jpg&#34; onerror=&#34;x"', html_str)

	def test_fonts_come_from_commera_assets(self):
		html_str = self.render_product_card(display_name="Brake pads").args[0]

		for url in CARD_FONTS:
			with self.subTest(url=url):
				self.assertIn(f'url("{url}")', html_str)
				path = frappe.get_app_path("commera", "public", url.removeprefix("/assets/commera/"))
				self.assertTrue(os.path.isfile(path))
		self.assertIn('font-family: "OpenSans", "Commera Emoji", sans-serif', html_str)
		self.assertNotIn("local(", html_str)

	def test_the_product_photo_is_a_site_file(self):
		variant = get_published_variant()
		if not variant:
			self.skipTest("No published Style Attribute Variant available.")
		photo = make_public_file(self, f"og-test-{frappe.generate_hash(length=10)}.jpg")

		with (
			patch.object(generator, "get_preview_from_html", return_value=b"jpg") as preview,
			patch("commera.product_detail.get_product_detail", return_value=detail_with_image(photo)),
		):
			doc = frappe.get_doc("Style Attribute Variant", variant.name)
			generator.render_card_for_doc("Style Attribute Variant", doc)

		self.assertIn(f'<img class="photo" src="{photo}"', preview.call_args.args[0])

	def test_an_og_image_template_fragment_gets_the_card_page(self):
		variant = get_published_variant()
		if not variant:
			self.skipTest("No published Style Attribute Variant available.")
		use_og_template(self, "<div style='display:flex'>{{ display_name | e }}</div>")

		with patch.object(generator, "get_preview_from_html", return_value=b"jpg") as preview:
			doc = frappe.get_doc("Style Attribute Variant", variant.name)
			generator.render_card_for_doc("Style Attribute Variant", doc)

		html_str = preview.call_args.args[0]
		self.assertIn('<html lang="', html_str)
		self.assertIn(CARD_FONTS[0], html_str)
		self.assertIn(f"<div style='display:flex'>{escape(generator.get_card_title(doc))}", html_str)

	def test_a_template_without_a_doctype_still_gets_the_content_policy_first(self):
		self.assertTrue(
			generator.with_content_policy("<html><body>x</body></html>").startswith(generator.CONTENT_POLICY)
		)


class TestStoreCardPage(IntegrationTestCase):
	def test_the_card_carries_the_store_name_and_the_logo_url(self):
		html_str = generator.build_store_card_html()

		self.assertIn(escape(seo.get_store_name()), html_str)
		self.assertIn(f'src="{generator.card_image_url(branding.get_brand_assets().logo)}"', html_str)

	def test_a_remote_logo_is_left_out(self):
		remote = frappe._dict(logo="https://cdn.example.com/logo.png")
		with patch.object(generator, "get_brand_assets", return_value=remote):
			html_str = generator.build_store_card_html()

		self.assertNotIn("cdn.example.com", html_str)
		self.assertNotIn('class="logo"', html_str)


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
		expected = f"{seo.get_site_currency()} {flt(amount):.2f}" if amount else ""
		self.assertEqual(context["price"], expected)

	def test_context_shape(self):
		variant_doc = frappe.get_doc("Style Attribute Variant", self.variant.name)
		context = generator.build_variant_card_context(variant_doc)
		for key in ("store_name", "display_name", "brand", "price", "photo_url", "photo_data_uri", "doc"):
			self.assertIn(key, context)
		self.assertIs(context["doc"], variant_doc)
		self.assertEqual(context["photo_data_uri"], context["photo_url"])
		self.assertEqual(context["store_name"], seo.get_store_name())


class TestClearOldCards(IntegrationTestCase):
	"""The cache key embeds `modified`, so every edit strands a card; clear_old_cards is the only bound."""

	def setUp(self):
		self.cache_dir = os.path.join(get_files_path(is_private=False), "og-cache")
		os.makedirs(self.cache_dir, exist_ok=True)

	def write_card(self, age_days, suffix=".jpg"):
		path = os.path.join(self.cache_dir, f"og-test-{frappe.generate_hash(length=12)}{suffix}")
		with open(path, "wb") as card_file:
			card_file.write(b"\xff\xd8\xff")
		aged = time.time() - (age_days * 86400)
		os.utime(path, (aged, aged))
		self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
		return path

	def test_stale_cards_and_unfinished_writes_are_pruned_and_fresh_ones_survive(self):
		stale = [self.write_card(45, suffix) for suffix in (".jpg", ".png", ".jpg.tmp-abcd1234")]
		fresh = self.write_card(age_days=1)

		generator.clear_old_cards(days=30)

		self.assertFalse(any(os.path.exists(path) for path in stale))
		self.assertTrue(os.path.exists(fresh))

	def test_cutoff_is_the_days_argument_not_the_default(self):
		card = self.write_card(age_days=10)
		generator.clear_old_cards(days=30)
		self.assertTrue(os.path.exists(card))
		generator.clear_old_cards(days=5)
		self.assertFalse(os.path.exists(card))

	def test_other_files_are_left_alone(self):
		bystander = self.write_card(age_days=365, suffix=".txt")
		generator.clear_old_cards(days=30)
		self.assertTrue(os.path.exists(bystander))

	def test_missing_cache_dir_is_a_no_op(self):
		with patch(
			"commera.og.generator.get_files_path",
			return_value=os.path.join(self.cache_dir, f"nope-{frappe.generate_hash(length=8)}"),
		):
			generator.clear_old_cards(days=30)


def detail_with_image(image_url):
	return {
		"product": frappe._dict(brand=""),
		"sale_price": None,
		"default_price": None,
		"images": [image_url],
	}
