# Copyright (c) 2026, company@bwhstudios.com and contributors
# See license.txt

"""OG cards through the real headless Chromium. Skipped where the bench has no Chromium, as on CI."""

import glob
import os
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from unittest import skipUnless

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_files_path
from PIL import Image

from commera.localization import pin_localization, resolve
from commera.og import generator
from commera.tests.test_localization import use_storefront_languages

PHOTO_COLOUR = (40, 120, 220)
TITLE = "حذاء Nike Air Max الرياضي"


def chromium_available():
	conf = frappe.get_common_site_config()
	if conf.get("chromium_websocket_url") or shutil.which(conf.get("chromium_path") or "-"):
		return True
	return bool(glob.glob(os.path.join(frappe.utils.get_bench_path(), "chromium", "*", "headless_shell*")))


@skipUnless(chromium_available(), "No Chromium on this bench; CI does not download one.")
class TestChromiumRender(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.photo_url = self.make_photo()

	def make_photo(self):
		name = f"og-test-photo-{frappe.generate_hash(length=10)}.png"
		path = os.path.join(get_files_path(is_private=False), name)
		Image.new("RGB", (900, 900), PHOTO_COLOUR).save(path, format="PNG")
		self.addCleanup(os.remove, path)
		return generator.card_image_url(f"/files/{name}")

	def render(self, path, **context):
		with pin_localization(resolve(path)[0]):
			html_str = generator.render_card_html(generator.BUNDLED_CARD_TEMPLATE, context)
			jpeg = generator.render_card_image(html_str)
		card = Image.open(BytesIO(jpeg))
		self.assertEqual((card.format, card.size), ("JPEG", (1200, 630)))
		return card.convert("RGB")

	def test_an_arabic_card_is_right_to_left_and_an_english_one_left_to_right(self):
		arabic = self.render("/ar", display_name=TITLE, photo_url=self.photo_url)
		english = self.render("/", display_name="Premium Brake Pads", photo_url=self.photo_url)

		self.assertTrue(is_colour(arabic.getpixel((300, 315)), PHOTO_COLOUR), "the photo is on the left")
		self.assertTrue(is_colour(english.getpixel((900, 315)), PHOTO_COLOUR), "the photo is on the right")
		arabic_text = ink_box(arabic, (630, 40, 1200, 400))
		english_text = ink_box(english, (0, 40, 570, 400))
		self.assertGreater(arabic_text[2], 1100, "right-to-left text ends on the right")
		self.assertLess(english_text[0], 100, "left-to-right text starts on the left")
		self.assertGreater(ink_share(arabic, (630, 40, 1200, 400)), 0.02, "the Arabic text drew nothing")

	def test_emoji_draw_in_colour(self):
		plain = self.render("/", display_name="Brake pads")
		emoji = self.render("/", display_name="Brake pads 🔥 👨‍👩‍👧‍👦 🇦🇪 1️⃣")

		self.assertGreater(colour_share(emoji) - colour_share(plain), 0.002)

	def test_the_renderer_makes_no_outbound_request(self):
		with RequestLog() as log:
			page = f"""<!doctype html><html><head>
				<link rel="stylesheet" href="{log.url}/style.css">
				<style>@font-face {{ font-family: X; src: url("{log.url}/font.woff2"); }}
				body {{ font-family: X; background: url("{log.url}/background.png"); }}</style>
				<script src="{log.url}/script.js"></script>
				</head><body><img src="{log.url}/image.png">x</body></html>"""
			generator.render_card_image(page)
			with pin_localization(resolve("/")[0]):
				generator.render_card_image(
					generator.render_card_html(
						generator.BUNDLED_CARD_TEMPLATE, {"display_name": f'"><img src={log.url}/title.png>'}
					)
				)
			self.assertEqual(log.paths, [])

			# The log does see a request when the page has no content policy.
			generator.get_preview_from_html(page, format="jpg", width=1200, height=630)
			self.assertIn("/image.png", log.paths)


class RequestLog:
	"""A local HTTP server that lists the paths it is asked for."""

	def __enter__(self):
		paths = self.paths = []

		class Handler(BaseHTTPRequestHandler):
			def do_GET(self):
				paths.append(self.path)
				self.send_response(404)
				self.end_headers()

			def log_message(self, *args):
				pass

		self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
		self.url = f"http://127.0.0.1:{self.server.server_port}"
		threading.Thread(target=self.server.serve_forever, daemon=True).start()
		return self

	def __exit__(self, *args):
		self.server.shutdown()
		self.server.server_close()


def is_colour(pixel, colour, tolerance=24):
	return all(abs(a - b) <= tolerance for a, b in zip(pixel, colour, strict=True))


def ink_box(card, box):
	"""The bounding box, on the card, of what is drawn in `box` on the dark card background."""
	left, top, _right, _bottom = box
	found = card.crop(box).convert("L").point(lambda value: 255 if value > 128 else 0).getbbox()
	return (found[0] + left, found[1] + top, found[2] + left, found[3] + top)


def ink_share(card, box):
	inked = card.crop(box).convert("L").point(lambda value: 255 if value > 128 else 0)
	return inked.histogram()[255] / (inked.width * inked.height)


def colour_share(card):
	"""The share of strongly coloured pixels. Text is white or grey; emoji are not."""
	pixels = card.getdata()
	return sum(1 for pixel in pixels if max(pixel) - min(pixel) > 80) / len(pixels)
