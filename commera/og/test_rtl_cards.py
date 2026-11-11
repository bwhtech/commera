# Copyright (c) 2026, company@bwhstudios.com and contributors
# See license.txt

"""Right-to-left OG cards, through the real Node/Satori subprocess."""

import json
import subprocess
from io import BytesIO
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from PIL import Image, ImageChops

from commera.localization import pin_localization, resolve
from commera.og import generator
from commera.shop_themes.render import render_themed_template
from commera.tests.test_localization import use_storefront_languages
from commera.www import og_image_render

PRODUCT_CARD = {
	"store_name": "متجر الخليج",
	"display_name": "حذاء Nike Air Max 270 الرياضي (مقاس 42)",
	"brand": "Nike",
	"price": "SAR 499.00",
}
LATIN_PRODUCT_CARD = {
	"store_name": "Gulf Store",
	"display_name": "Premium Brake Pads - Black",
	"brand": "Lifestyle",
	"price": "SAR 499.00",
}
STORE_CARD = {
	"store_name": "متجر الخليج للأحذية",
	"tagline": "أحذية رياضية أصلية من Nike و Adidas، شحن مجاني فوق 200 ريال.",
	"site_host": "shop.example.com",
}
LATIN_STORE_CARD = {
	"store_name": "Gulf Store",
	"tagline": "Original sneakers.",
	"site_host": "shop.example.com",
}

# The product card's title and store name rows, and the store card's name and tagline rows.
PRODUCT_TEXT_BOX = (0, 40, 1200, 300)
STORE_TEXT_BOX = (0, 60, 1200, 330)

# The pipeline before right-to-left support: satori-html straight into Satori, Open Sans only.
PLAIN_SATORI = """
import { readFileSync } from 'node:fs';
import { Resvg } from '@resvg/resvg-js';
import satori from 'satori';
import { html } from 'satori-html';
const payload = JSON.parse(readFileSync(0, 'utf8'));
const fonts = payload.fonts.map((font) => ({ ...font, data: readFileSync(font.path) }));
const svg = await satori(html(payload.html), { width: payload.width, height: payload.height, fonts });
process.stdout.write(new Resvg(svg, { fitTo: { mode: 'width', value: payload.width } }).render().asPng());
"""

# Lists the words of a prepared card from left to right, as Satori places them.
VISUAL_ORDER = """
import { readFileSync } from 'node:fs';
import { html } from 'satori-html';
const { prepareTree } = await import(process.argv[1]);
const payload = JSON.parse(readFileSync(0, 'utf8'));
const words = (node) => {
	if (typeof node === 'string') return node.trim() ? [node] : [];
	if (Array.isArray(node)) return node.flatMap(words);
	const children = [].concat(node?.props?.children ?? []);
	const style = node?.props?.style ?? {};
	return (style.flexDirection === 'row-reverse' ? children.reverse() : children).flatMap(words);
};
process.stdout.write(JSON.stringify(words(prepareTree(html(payload.html), payload.direction))));
"""


class TestRightToLeftCards(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"))

	def test_an_arabic_product_card_draws_its_text_on_the_right(self):
		card = render_card(generator.BUNDLED_CARD_TEMPLATE, PRODUCT_CARD, "/ar")

		self.assertGreater(text_coverage(card, PRODUCT_TEXT_BOX), 0.02, "the Arabic text drew nothing")
		self.assertGreater(ink_box(card, PRODUCT_TEXT_BOX)[2], 1100, "right-to-left text ends on the right")

	def test_an_arabic_store_card_draws_its_name_and_tagline_on_the_right(self):
		card = render_card(generator.STORE_CARD_TEMPLATE, STORE_CARD, "/ar")

		self.assertGreater(text_coverage(card, STORE_TEXT_BOX), 0.02, "the Arabic text drew nothing")
		self.assertGreater(ink_box(card, STORE_TEXT_BOX)[2], 1080, "right-to-left text ends on the right")

	def test_a_right_to_left_card_mirrors_the_latin_layout(self):
		latin = ink_box(
			render_card(generator.BUNDLED_CARD_TEMPLATE, LATIN_PRODUCT_CARD, "/"), PRODUCT_TEXT_BOX
		)
		mirrored = ink_box(
			render_card(generator.BUNDLED_CARD_TEMPLATE, LATIN_PRODUCT_CARD, "/ar"), PRODUCT_TEXT_BOX
		)

		self.assertLess(latin[0], 100)
		self.assertGreater(mirrored[2], 1100)
		self.assertAlmostEqual(latin[2] - latin[0], mirrored[2] - mirrored[0], delta=5)

	def test_latin_cards_are_unchanged(self):
		for template, context in (
			(generator.BUNDLED_CARD_TEMPLATE, LATIN_PRODUCT_CARD),
			(generator.STORE_CARD_TEMPLATE, LATIN_STORE_CARD),
		):
			html_str = render_themed_template(template, context)
			with pin_localization(resolve("/")[0]):
				png_bytes = generator.render_og_png(
					html_str, generator.DEFAULT_OG_WIDTH, generator.DEFAULT_OG_HEIGHT
				)
			self.assertEqual(png_bytes, run_node(PLAIN_SATORI, plain_payload(html_str)), template)

	def test_mixed_text_reads_in_visual_order(self):
		rtl_title = "<div>حذاء Nike Air Max 270 بسعر 499 درهم (مقاس 42).</div>"
		ltr_title = "<div>Linen shirt قميص الكتان 2024</div>"

		self.assertEqual(
			visual_order(rtl_title, "rtl"),
			[".", "(", "42", "مقاس", ")", "درهم", "499", "بسعر", "Nike Air Max 270", "حذاء"],
		)
		self.assertEqual(visual_order(ltr_title, "ltr"), ["Linen shirt ", "2024", "الكتان", "قميص"])
		# Arabic-Indic digits read left to right too.
		self.assertEqual(visual_order("<div>سعر \u0661\u0662</div>", "rtl"), ["\u0661", "\u0662", "سعر"])

	def test_brackets_digits_and_brands(self):
		cases = (
			("حذاء Nike (Air Max) الرياضي", ["الرياضي", "Nike (Air Max)", "حذاء"]),
			("حذاء Nike ١٢ الرياضي", ["الرياضي", "\u0661", "\u0662", "Nike", "حذاء"]),
			("حذاء Nike ۱۲ الرياضي", ["الرياضي", "Nike ", "\u06f1", "\u06f2", "حذاء"]),
			("حذاء Nike 12 الرياضي", ["الرياضي", "Nike 12", "حذاء"]),
			("حذاء Nike (Air [Max]) الرياضي", ["الرياضي", "Nike (Air [Max])", "حذاء"]),
			("حذاء Nike-Air, Inc. الرياضي", ["الرياضي", ".", "Nike-Air, Inc", "حذاء"]),
			("Nike (Air Max) 12", ["Nike (Air Max) 12"]),
		)
		for text, expected in cases:
			with self.subTest(text=text):
				self.assertEqual(visual_order(f"<div>{text}</div>", "rtl"), expected)

	def test_astral_characters_follow_fribidi_visual_order(self):
		# FriBidi's left-to-right visual order, with RTL words kept logical for HarfBuzz.
		cases = (
			("حذاء Nike 🔥 الرياضي", ["الرياضي", "🔥", "Nike", "حذاء"]),
			("متجر الخليج 🛍️ Nike", ["Nike", "🛍️", "الخليج", "متجر"]),
			("فروشگاه آنلاین 🛒 Apple", ["Apple", "🛒", "آنلاین", "فروشگاه"]),
			("حذاء Nike 👨‍👩‍👧‍👦 الرياضي", ["الرياضي", "👨‍👩‍👧‍👦", "Nike", "حذاء"]),
			("حذاء Nike 𠀀 الرياضي", ["الرياضي", "Nike 𠀀", "حذاء"]),
			("حذاء Nike 🇦🇪 الرياضي", ["الرياضي", "Nike 🇦🇪", "حذاء"]),
			("حذاء Nike 👍🏽 الرياضي", ["الرياضي", "👍🏽", "Nike", "حذاء"]),
			("حذاء Nike 1️⃣ الرياضي", ["الرياضي", "Nike 1️⃣", "حذاء"]),
		)
		for text, expected in cases:
			with self.subTest(text=text):
				self.assertEqual(visual_order(f"<div>{text}</div>", "rtl"), expected)

	def test_custom_centered_element_stays_centered(self):
		html_str = """<div style="display:flex;width:1200px;height:630px;background:white">
		<div style="display:flex;position:absolute;left:50%;top:100px;transform:translateX(-50%);
		width:100px;height:100px;background:red"></div></div>"""
		with pin_localization(resolve("/ar")[0]):
			card = Image.open(BytesIO(generator.render_og_png(html_str, 1200, 630))).convert("RGB")
		self.assertEqual(card.getpixel((550, 120)), (255, 0, 0))
		self.assertEqual(card.getpixel((649, 120)), (255, 0, 0))
		self.assertEqual(card.getpixel((650, 120)), (255, 255, 255))

	def test_direction_aware_templates_keep_their_layout(self):
		for marker, direction, red_x in (
			('data-og-no-mirror="true"', "row", 50),
			("", "row-reverse", 1150),
		):
			html_str = f"""<div {marker} style="display:flex;flex-direction:{direction};
			width:1200px;height:630px;background:white">
			<div style="display:flex;width:100px;height:100px;background:red"></div></div>"""
			with pin_localization(resolve("/ar")[0]):
				card = Image.open(BytesIO(generator.render_og_png(html_str, 1200, 630))).convert("RGB")
			self.assertEqual(card.getpixel((red_x, 50)), (255, 0, 0))
			self.assertEqual(card.getpixel((1200 - red_x, 50)), (255, 255, 255))

	def test_a_right_to_left_store_card_has_its_own_cache_file(self):
		self.addCleanup(setattr, frappe.local.flags, "redirect_location", None)
		cards = set()
		with (
			patch.object(og_image_render, "build_store_card_html", return_value="<div>Gulf Store</div>"),
			patch.object(og_image_render, "render_og_png", return_value=b"png"),
			patch.object(og_image_render, "write_cache"),
		):
			for path in ("/", "/ar"):
				with pin_localization(resolve(path)[0]), self.assertRaises(frappe.Redirect):
					og_image_render.serve_store_card()
				cards.add(frappe.local.flags.redirect_location)
		self.assertEqual(len(cards), 2)

	def test_arabic_and_hebrew_fonts_load_only_for_their_script(self):
		def families(text):
			return {font["name"] for font in generator.card_fonts(f"<div>{text}</div>")}

		self.assertEqual(families("Brake pads"), {"OpenSans"})
		self.assertEqual(families("فحمات فرامل"), {"OpenSans", "IBM Plex Sans Arabic"})
		self.assertEqual(families("נעליים"), {"OpenSans", "IBM Plex Sans Hebrew"})


def render_card(template, context, path):
	html_str = render_themed_template(template, context)
	with pin_localization(resolve(path)[0]):
		png_bytes = generator.render_og_png(html_str, generator.DEFAULT_OG_WIDTH, generator.DEFAULT_OG_HEIGHT)
	return Image.open(BytesIO(png_bytes)).convert("RGB")


def ink_box(card, box):
	"""The bounding box, on the card, of what is drawn in `box`."""
	left, top, _right, _bottom = box
	found_left, found_top, found_right, found_bottom = ink(card, box).getbbox()
	return (found_left + left, found_top + top, found_right + left, found_bottom + top)


def text_coverage(card, box):
	"""The share of `box` that is drawn on."""
	inked = ink(card, box)
	return sum(inked.histogram()[1:]) / (inked.width * inked.height)


def ink(card, box):
	"""A mask of the pixels in `box` that differ from the background, read at its bottom-right corner."""
	region = card.crop(box)
	solid = Image.new("RGB", region.size, region.getpixel((region.width - 1, region.height - 1)))
	return ImageChops.difference(region, solid).convert("L").point(lambda value: 255 if value > 40 else 0)


def plain_payload(html_str):
	fonts = [font for font in generator.card_fonts(html_str) if font["name"] == "OpenSans"]
	return {"html": html_str, "width": 1200, "height": 630, "fonts": fonts}


def visual_order(html_str, direction):
	script_path = frappe.get_app_path("commera", "og", "og_bidi.mjs")
	return json.loads(run_node(VISUAL_ORDER, {"html": html_str, "direction": direction}, script_path))


def run_node(script, payload, *args):
	result = subprocess.run(  # nosemgrep: frappe-subprocess-exec
		["node", "--input-type=module", "-e", script, *args],
		input=json.dumps(payload).encode(),
		capture_output=True,
		cwd=frappe.get_app_path("commera"),
		timeout=30,
		check=True,
	)
	return result.stdout
