"""Legacy pages and the summer theme link through url() and switch through switch_url()."""

import re
from html.parser import HTMLParser
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase
from frappe.website.serve import get_response_content
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.admin.theme import activate_theme
from commera.localization.routing import localize_request
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_product_details import ProductDetailPriceTestCase
from commera.tests.test_store_frame_translation import SECTION, SETTINGS

APP = Path(frappe.get_app_path("commera"))
SURFACES = ("templates", "www", "themes/summer_theme", "public/themes/summer_theme/js")
# Merchant-editable fallback text for /llms.txt, not a link the page builds.
SKIPPED = {"www/llms.py"}
# The shared macros, which the theme engine imports; the pages here use only the language one.
SWITCHER_MACROS = "templates/macros/language_switcher.html"
THEMES = ("Shop Default Theme", "Summer Theme")
HAND_BUILT_PREFIX = re.compile(
	r"frappe\.(?:local\.)?lang\s*(?:~|\}\}\s*/|==)"
	r"|/\{\{\s*(?:frappe\.lang|language)\b"
	r"|~\s*\(?(?:frappe\.lang|language)\b(?![.\w])"
	r"|root_prefix"
	r"|\$\{(?:lang|language|settings\.language)\}"
	r"|\{frappe\.local\.lang\}"
	r"""|['"`(]/(?:en|ar)(?:/|['"`)])"""
)
UNPREFIXED_LINK = re.compile(r'(?:href|action)="/(?!/|assets/|files/|api/|login\b)')
JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.S)
NOT_PAGES = ("/assets/", "/files/", "/api/", "/login")


class TestLegacyLinkSources(IntegrationTestCase):
	def test_no_surface_builds_a_language_prefix_by_hand(self):
		for path, text in read_surfaces():
			with self.subTest(path):
				self.assertNotRegex(text, HAND_BUILT_PREFIX)
				self.assertNotRegex(text, UNPREFIXED_LINK)

	def test_no_surface_offers_a_market_or_country_switcher(self):
		for path, text in read_surfaces():
			if path != SWITCHER_MACROS:
				with self.subTest(path):
					self.assertNotIn("country_switcher", text)
					self.assertNotIn("get_country_choices", text)


class TestLegacyLocalizedLinks(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		use_storefront_languages(self, "en", published=("en", "ar", "fr"), unpublished=("de",))
		self.route = self.make_priced_variant("LINKS", default_rate=30)
		self.set_footer_link("/en/page/shipping")

	def test_every_internal_link_carries_the_page_language(self):
		for theme in THEMES:
			activate_theme(theme)
			for path in ("/ar", f"/ar/products/{self.route}", "/ar/products"):
				with self.subTest(theme=theme, path=path):
					links = page_links(self.render_page(path))
					self.assertIn("/ar/page/shipping", links)
					self.assertGreater(len(links), 5)
					for href in links:
						self.assertRegex(href, r"^/ar(?:[/?#]|$)")

	def test_the_switcher_lists_published_languages_and_keeps_the_query(self):
		for theme in THEMES:
			activate_theme(theme)
			with self.subTest(theme=theme):
				html = self.render_page("/ar/products?brands=Acme&sort=price")
				self.assertEqual(
					switcher_links(html),
					{
						"en": "/products?brands=Acme&sort=price",
						"ar": "/ar/products?brands=Acme&sort=price",
						"fr": "/fr/products?brands=Acme&sort=price",
					},
				)

	def test_a_one_language_store_shows_no_switcher(self):
		use_storefront_languages(self, "en", published=("en",))
		for theme in THEMES:
			activate_theme(theme)
			with self.subTest(theme=theme):
				self.assertEqual(switcher_links(self.render_page("/products")), {})

	def set_footer_link(self, link_url):
		"""One footer section with one link, written straight to the database."""
		section = frappe.get_doc(
			{
				"doctype": SECTION,
				"section_title": f"Help {frappe.generate_hash(length=8)}",
				"enabled": 1,
				"footer_links": [
					{"link_label": "Shipping", "link_url": link_url, "link_order": 1, "enabled": 1}
				],
			}
		).insert(ignore_permissions=True)
		frappe.db.delete("Footer Section Mapping", {"parent": SETTINGS, "parentfield": "footer_sections"})
		frappe.get_doc(
			{
				"doctype": "Footer Section Mapping",
				"parent": SETTINGS,
				"parenttype": SETTINGS,
				"parentfield": "footer_sections",
				"idx": 1,
				"footer_section": section.name,
				"section_order": 1,
				"enabled": 1,
			}
		).db_insert()
		frappe.clear_document_cache(SETTINGS, SETTINGS)
		self.addCleanup(frappe.clear_document_cache, SETTINGS, SETTINGS)

	def render_page(self, path):
		"""The HTML a guest gets for `path`, routed and localized as a real request."""
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
		self.addCleanup(frappe.clear_cache)
		frappe.local.request = Request(EnvironBuilder(path=path).get_environ())
		frappe.local.form_dict = frappe._dict(frappe.local.request.args)
		frappe.local.request_cache.clear()
		# Memoised per request: a real request starts without it.
		frappe.local.commera_storefront_menu = None
		# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
		frappe.set_user("Guest")
		try:
			localize_request()
			return get_response_content(frappe.local.request.path)
		finally:
			# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
			frappe.set_user("Administrator")


class AnchorParser(HTMLParser):
	"""Each <a> and <form>'s link, with the anchor's hreflang when it has one."""

	def __init__(self):
		super().__init__()
		self.links = []

	def handle_starttag(self, tag, attrs):
		attrs = dict(attrs)
		link = attrs.get("href") if tag == "a" else attrs.get("action") if tag == "form" else None
		if link is not None:
			self.links.append((link, attrs.get("hreflang")))


def parse_links(html):
	parser = AnchorParser()
	parser.feed(html)
	return parser.links


def page_links(html):
	"""Same-site page links, leaving out the switcher's links to other languages."""
	return [
		href
		for href, hreflang in parse_links(html)
		if href.startswith("/") and not href.startswith(("//", *NOT_PAGES)) and not hreflang
	]


def switcher_links(html):
	return {hreflang: href for href, hreflang in parse_links(html) if hreflang}


def read_surfaces():
	for surface in SURFACES:
		for path in sorted((APP / surface).rglob("*")):
			name = str(path.relative_to(APP))
			if path.suffix in (".html", ".py", ".js") and not path.name.endswith(".min.js"):
				if name not in SKIPPED:
					yield name, JINJA_COMMENT.sub("", path.read_text())
