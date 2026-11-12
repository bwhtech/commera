# Copyright (c) 2026, company@bwhstudios.com and contributors
# See license.txt

"""Emoji and astral characters on OG cards, through the real Node/Satori subprocess."""

import json
from io import BytesIO

import frappe
from frappe.tests import IntegrationTestCase
from PIL import Image

from commera.localization import pin_localization, resolve
from commera.og import generator
from commera.og.test_rtl_cards import ink_box, render_card, run_node
from commera.tests.test_localization import use_storefront_languages

EMOJI = "🔥 🛍️ 👨‍👩‍👧‍👦 🇦🇪 👍🏽 1️⃣"
PRODUCT_CARDS = {
	"/": {"store_name": "Gulf Store", "display_name": "Running shoes", "brand": "Nike"},
	"/ar": {"store_name": "متجر الخليج", "display_name": "حذاء رياضي", "brand": "Nike"},
}
STORE_CARDS = {
	"/": {"store_name": "Gulf Store", "tagline": "Original sneakers", "site_host": "shop.example.com"},
	"/ar": {"store_name": "متجر الخليج", "tagline": "أحذية رياضية أصلية", "site_host": "shop.example.com"},
}

# Each sequence and the Twemoji file that draws it as one graphic.
SEQUENCES = (
	("🔥", "1f525"),
	("🛍️", "1f6cd"),
	("🛒", "1f6d2"),
	("❤", "2764"),
	("👨‍👩‍👧‍👦", "1f468-200d-1f469-200d-1f467-200d-1f466"),
	("🇦🇪", "1f1e6-1f1ea"),
	("👍🏽", "1f44d-1f3fd"),
	("1️⃣", "31-20e3"),
	("#️⃣", "23-20e3"),
	("🏳️‍🌈", "1f3f3-fe0f-200d-1f308"),
	("👁️‍🗨️", "1f441-200d-1f5e8"),
	("🏴󠁧󠁢󠁥󠁮󠁧󠁿", "1f3f4-e0067-e0062-e0065-e006e-e0067-e007f"),
)

EMOJI_SIZE = 100


class TestEmojiCards(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"))

	def test_product_and_store_cards_draw_their_emoji(self):
		for template, cards, field in (
			(generator.BUNDLED_CARD_TEMPLATE, PRODUCT_CARDS, "display_name"),
			(generator.STORE_CARD_TEMPLATE, STORE_CARDS, "store_name"),
		):
			for path, context in cards.items():
				with self.subTest(template=template, path=path):
					plain = render_card(template, context, path)
					with_emoji = render_card(template, {**context, field: f"{context[field]} {EMOJI}"}, path)

					# Twemoji are coloured; a missing glyph is a box in the text colour.
					self.assertGreater(colour_share(with_emoji) - colour_share(plain), 0.01)

	def test_each_sequence_is_one_twemoji_graphic(self):
		script = """
import { readFileSync } from 'node:fs';
const { emojiKey } = await import(process.argv[1]);
const sequences = JSON.parse(readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(sequences.map(emojiKey)));
"""
		sequences = [sequence for sequence, _key in SEQUENCES]
		keys = json.loads(run_node(script, sequences, glyphs_script()))

		self.assertEqual(keys, [key for _sequence, key in SEQUENCES])

	def test_each_sequence_draws_one_graphic(self):
		for sequence, _key in SEQUENCES:
			for path in ("/", "/ar"):
				with self.subTest(sequence=sequence, path=path):
					card = render_text(sequence, path)
					left, _top, right, _bottom = ink_box(card, (0, 0, card.width, card.height))

					# A glyph or a box takes the text colour; an image does not.
					self.assertEqual(render_png(sequence, path, "#e00"), render_png(sequence, path))
					self.assertLess(right - left, EMOJI_SIZE * 1.3, "drawn as more than one graphic")

	def test_astral_characters_without_a_font_draw_no_box(self):
		for path in ("/", "/ar"):
			with self.subTest(path=path):
				card = render_text("𠀀𠮷", path)
				self.assertIsNone(card.convert("L").point(lambda value: value < 200 and 255).getbbox())

		for without, with_astral in (
			("حذاء Nike الرياضي", "حذاء Nike 𠀀 الرياضي"),
			("Nike Air", "Nike 𠮷 Air"),
		):
			self.assertEqual(render_png(with_astral, "/ar"), render_png(without, "/ar"))

	def test_supported_bases_survive_unsupported_astral_marks(self):
		for plain, marked in (
			("A", "A\U000e0100"),
			# U+1D165 is the combining musical stem.
			("A", "A\U0001d165"),
			("A\u0301", "A\u0301\U000e0100"),
			("حذاء", "حذاء\U000e0100"),
			(
				"حذاء 🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
				"حذاء\U000e0100 🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
			),
		):
			for path in ("/", "/ar"):
				with self.subTest(plain=plain, marked=marked, path=path):
					self.assertEqual(render_png(marked, path), render_png(plain, path))

	def test_renderable_text(self):
		script = """
import { readFileSync } from 'node:fs';
const { renderableText } = await import(process.argv[1]);
const texts = JSON.parse(readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(texts.map(renderableText)));
"""
		cases = (
			("Brake pads", "Brake pads"),
			# Mathematical bold SALE.
			("\U0001d412\U0001d400\U0001d40b\U0001d404 🔥 now", "SALE 🔥 now"),
			("Nike 𠀀 الرياضي", "Nike الرياضي"),
			("a 𠀀 𠀁 b", "a b"),
			("𠮷野家", "野家"),
			("👨‍👩‍👧‍👦🇦🇪🏴󠁧󠁢󠁥󠁮󠁧󠁿", "👨‍👩‍👧‍👦🇦🇪🏴󠁧󠁢󠁥󠁮󠁧󠁿"),
		)
		texts = [text for text, _expected in cases]
		actual = json.loads(run_node(script, texts, glyphs_script()))

		self.assertEqual(actual, [expected for _text, expected in cases])


def render_png(text, path, colour="#000"):
	html_str = f"""<div style="display:flex;width:400px;height:200px;padding:40px;background:#fff;
	color:{colour};font-family:'OpenSans';font-size:{EMOJI_SIZE}px">{frappe.utils.escape_html(text)}</div>"""
	with pin_localization(resolve(path)[0]):
		return generator.render_og_png(html_str, 400, 200)


def render_text(text, path):
	return Image.open(BytesIO(render_png(text, path))).convert("RGB")


def colour_share(card):
	"""The share of the card's pixels with a strong colour; text, boxes and backgrounds are grey."""
	hsv = card.convert("HSV")
	saturated = hsv.getchannel("S").point(lambda value: 255 if value > 120 else 0)
	bright = hsv.getchannel("V").point(lambda value: 255 if value > 80 else 0)
	coloured = Image.composite(saturated, Image.new("L", card.size), bright)
	return sum(coloured.histogram()[1:]) / (card.width * card.height)


def glyphs_script():
	return frappe.get_app_path("commera", "og", "og_glyphs.mjs")
