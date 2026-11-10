"""Legacy pages and the summer theme link through url() and switch through switch_url()."""

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_request_site_address
from frappe.website.serve import get_response_content
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera import utils
from commera.api.admin.theme import activate_theme
from commera.api.payments import get_confirmation_url
from commera.localization.routing import localize_request
from commera.tests.test_content_translation import use_storefront_language
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_order_access import make_website_user
from commera.tests.test_product_details import ProductDetailPriceTestCase
from commera.tests.test_store_frame_translation import SECTION, SETTINGS
from commera.website_context import update_website_context

APP = Path(frappe.get_app_path("commera"))
SURFACES = (
	"templates",
	"www",
	"themes/summer_theme",
	"public/themes/summer_theme/js",
	"api/payments.py",
	"api/storefront",
)
# Merchant-editable fallback text for /llms.txt, not a link the page builds.
SKIPPED = {"www/llms.py"}
# The shared macros, which the theme engine imports; the pages here use only the language one.
SWITCHER_MACROS = "templates/macros/language_switcher.html"
THEMES = ("Shop Default Theme", "Summer Theme")
ARABIC_TITLE = "قميص كتان"
# Product cards bind the producer's title in every language; a bare item_name drops it.
CARD_TITLES = {
	("Shop Default Theme", "/"): 'x-text="product.title || product.item_name"',
	("Shop Default Theme", "/account/wishlist"): 'x-text="item.title||item.item_name"',
	("Shop Default Theme", "/account/dashboard"): 'x-text="item.title || item.item_name"',
	("Summer Theme", "/account/wishlist"): 'x-text="wishlist_item.title || wishlist_item.item_name"',
}
BARE_ITEM_NAME = re.compile(r'x-text="(?:product|item|wishlist_item)\.item_name"')
ACCOUNT_PAGES = ("dashboard", "orders", "wishlist", "profile", "address")
HAND_BUILT_PREFIX = re.compile(
	r"frappe\.(?:local\.)?lang\s*(?:~|\}\}\s*/|==)"
	r"|/\{\{\s*(?:frappe\.lang|language)\b"
	r"|~\s*\(?(?:frappe\.lang|language)\b(?![.\w])"
	r"|root_prefix"
	r"|\$\{(?:lang|language|settings\.language)\}"
	r"|\{frappe\.local\.lang\}"
	r"""|['"`(]/(?:en|ar)(?:/|['"`)])"""
)
UNPREFIXED_LINK = re.compile(r"""(?:href|action)=["']/(?!/|assets/|files/|api/|login\b)""")
# A url() inside a JS string: |e leaves quotes and ${} live, so JS takes it through |tojson.
URL_IN_JS_STRING = re.compile(r"['`]\{\{\s*(?:switch_)?url\(")
# A relative path such as "products/x" resolves against /ar and /ar/ differently and drops the language.
RELATIVE_LINK = re.compile(r"""(?<![:\w-])(?:href|action)=["'](?![a-z][a-z0-9+.-]*:)[a-z]""")
JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.S)
NOT_PAGES = ("/assets/", "/files/", "/api/", "/login")


class TestLegacyLinkSources(IntegrationTestCase):
	def test_no_surface_builds_a_language_prefix_by_hand(self):
		for path, text in read_surfaces():
			with self.subTest(path):
				self.assertNotRegex(text, HAND_BUILT_PREFIX)
				self.assertNotRegex(text, UNPREFIXED_LINK)
				self.assertNotRegex(text, URL_IN_JS_STRING)
				self.assertNotRegex(text, RELATIVE_LINK)

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

	def test_legacy_account_pages_render_and_link_in_the_page_language(self):
		activate_theme("Shop Default Theme")
		user = make_website_user()
		for page in ACCOUNT_PAGES:
			with self.subTest(page):
				links = page_links(self.render_page(f"/ar/account/{page}", user))
				self.assertIn("/ar/account/orders", links)
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

	def test_product_cards_show_the_title_on_a_non_english_default_store(self):
		use_storefront_languages(self, "ar", published=("ar", "en"))
		product = frappe.db.get_value("Style Attribute Variant", {"route": self.route})
		frappe.db.set_value("Style Attribute Variant", product, "display_name", ARABIC_TITLE)
		[card] = utils.get_product_list(product_list=[product], page_length=1)
		self.assertEqual(card["title"], ARABIC_TITLE)

		user = make_website_user()
		for (theme, path), binding in CARD_TITLES.items():
			activate_theme(theme)
			with self.subTest(theme=theme, path=path):
				html = self.render_page(path, user)
				self.assertIn(binding, html)
				self.assertNotRegex(html, BARE_ITEM_NAME)

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

	def render_page(self, path, user="Guest"):
		"""The HTML `user` gets for `path`, routed and localized as a real request."""
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
		self.addCleanup(frappe.clear_cache)
		frappe.local.request = Request(EnvironBuilder(path=path).get_environ())
		frappe.local.form_dict = frappe._dict(frappe.local.request.args)
		frappe.local.request_cache.clear()
		# Memoised per request: a real request starts without it, and the next test too.
		frappe.local.commera_storefront_menu = None
		self.addCleanup(setattr, frappe.local, "commera_storefront_menu", None)
		# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
		frappe.set_user(user)
		try:
			localize_request()
			return get_response_content(frappe.local.request.path)
		finally:
			# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
			frappe.set_user("Administrator")


class TestServerBuiltLinks(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"))

	def test_the_payment_confirmation_url_has_no_default_language_prefix(self):
		self.assertEqual(
			get_confirmation_url("SAL-QTN-1&x", payment_mode="Cash On Delivery"),
			"/account/orders/confirmation?reference_id=SAL-QTN-1%26x&payment_mode=Cash+On+Delivery",
		)
		use_storefront_language(self, "ar")
		self.assertEqual(
			get_confirmation_url("SAL-QTN-1"), "/ar/account/orders/confirmation?reference_id=SAL-QTN-1"
		)


class TestSiteAddressUrl(IntegrationTestCase):
	def setUp(self):
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		frappe.local.request = Request(EnvironBuilder(path="/checkout").get_environ())

	def test_the_site_address_url_is_dropped_so_the_helper_shows(self):
		context = frappe._dict(url=quote(str(get_request_site_address(full_address=True)), safe="/:"))
		update_website_context(context)
		self.assertNotIn("url", context)

	def test_a_page_controllers_own_url_stays(self):
		# A payment page posts its form to the gateway it puts in `url`.
		context = frappe._dict(url="https://gateway.example/pay")
		update_website_context(context)
		self.assertEqual(context.url, "https://gateway.example/pay")


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
		root = APP / surface
		for path in [root] if root.is_file() else sorted(root.rglob("*")):
			name = str(path.relative_to(APP))
			if path.suffix in (".html", ".py", ".js") and not path.name.endswith(".min.js"):
				if name not in SKIPPED:
					yield name, JINJA_COMMENT.sub("", path.read_text())
