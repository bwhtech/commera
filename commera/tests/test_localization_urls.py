import json
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_url
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.localization import alternates, get_localization, switch_url, url
from commera.tests.test_localization import use_storefront_languages

SWITCHER = (
	'{% from "templates/macros/language_switcher.html" import language_switcher %}{{ language_switcher() }}'
)

MALICIOUS_QUERY = 'x="><img src=x onerror=alert(1)>'

# packages/storefront/test/url.test.js passes the same cases, so url() has one answer in both.
URL_CASES = Path(__file__).resolve().parents[2] / "packages" / "storefront" / "test" / "url-cases.json"


class LocaleUrlTestCase(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar", "fr"), unpublished=("de",))
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		self.addCleanup(frappe.set_user, frappe.session.user)
		frappe.set_user("Guest")
		self.open("/")

	def open(self, path, query_string=""):
		frappe.local.request = Request(EnvironBuilder(path=path, query_string=query_string).get_environ())
		frappe.local.form_dict = frappe._dict(frappe.local.request.args)
		frappe.local.request_cache.clear()


class TestUrl(LocaleUrlTestCase):
	def test_the_default_language_has_no_prefix(self):
		self.assertEqual(url("/products"), "/products")
		self.assertEqual(url("/"), "/")

	def test_a_page_in_another_language_adds_its_prefix(self):
		self.open("/ar/products")

		self.assertEqual(url("/products/blue-shirt"), "/ar/products/blue-shirt")
		self.assertEqual(url("/"), "/ar")

	def test_the_query_string_and_fragment_are_kept(self):
		self.open("/fr/cart")

		self.assertEqual(
			url("/products?category=shirts&sizes=M#grid"), "/fr/products?category=shirts&sizes=M#grid"
		)

	def test_a_path_that_names_a_language_moves_to_the_current_one(self):
		self.open("/ar/products")

		self.assertEqual(url("/en/page/about"), "/ar/page/about")
		self.assertEqual(url("/fr/page/about"), "/ar/page/about")
		self.open("/products")
		self.assertEqual(url("/en/page/about"), "/page/about")

	def test_links_outside_the_storefront_stay_as_they_are(self):
		self.open("/ar/products")

		for link in (
			"https://example.com/products",
			"//example.com/products",
			"mailto:shop@example.com",
			"#reviews",
			"products",
			"/files/size-guide.pdf",
			"/api/method/ping",
			"/assets/commera/logo.svg",
			"",
			None,
		):
			with self.subTest(link):
				self.assertEqual(url(link), link)

	def test_a_page_path_never_becomes_an_off_site_link(self):
		self.assertEqual(url("/ar/\\evil.com/x"), "/evil.com/x")
		self.assertEqual(url("/fr//evil.com/x"), "/evil.com/x")
		self.assertEqual(url("/%2F%2Fx"), "/%2F%2Fx")
		self.open("/ar/products")
		self.assertEqual(url("/en/\\/evil.com/x"), "/ar/evil.com/x")
		self.assertEqual(url("/%2F%2Fx"), "/ar/%2F%2Fx")

	def test_links_a_browser_reads_as_off_site_get_no_prefix(self):
		self.open("/ar/products")

		for link in ("/\\x", "/\\evil.com/x", "/\t/evil.com", " //evil.com", "///evil.com"):
			with self.subTest(link):
				self.assertEqual(url(link), link)

	def test_a_script_link_goes_nowhere(self):
		for link in (
			"javascript:alert(1)",
			" JavaScript:alert(1)",
			"java\nscript:alert(1)",
			"data:text/html,x",
		):
			with self.subTest(link):
				self.assertEqual(url(link), "#")
				self.assertEqual(switch_url(link, language="ar"), "#")

	def test_an_api_request_follows_its_lang_parameter(self):
		self.open("/api/method/commera.api.ping", "_lang=ar")

		self.assertEqual(url("/products"), "/ar/products")

	def test_jinja_has_url_and_switch_url(self):
		self.open("/ar/products", "sort_by=price")

		html = frappe.render_template("{{ url('/cart') }} {{ switch_url(language='fr') }}", {})

		self.assertEqual(html, "/ar/cart /fr/products?sort_by=price")


class TestUrlCases(IntegrationTestCase):
	def setUp(self):
		self.cases = json.loads(URL_CASES.read_text())
		languages = self.cases["languages"]
		use_storefront_languages(
			self, languages["default"], published=languages["published"], unpublished=languages["unpublished"]
		)
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		self.addCleanup(frappe.set_user, frappe.session.user)
		frappe.set_user("Guest")

	def test_each_page_resolves_the_localization_the_javascript_cases_give(self):
		for page, expected in self.cases["pages"].items():
			with self.subTest(page):
				open_page(page)
				localization = get_localization()
				self.assertEqual(localization.language.code, expected["language"])
				self.assertEqual(localization.root_prefix, expected["root_prefix"])
				self.assertEqual(list(localization.prefix_codes), expected["prefix_codes"])

	def test_url_gives_the_shared_answer_for_each_case(self):
		for case in self.cases["cases"]:
			with self.subTest(page=case["page"], path=case["path"]):
				open_page(case["page"])
				self.assertEqual(url(case["path"]), case["expected"])


def open_page(path):
	frappe.local.request = Request(EnvironBuilder(path=path).get_environ())
	frappe.local.form_dict = frappe._dict()
	frappe.local.request_cache.clear()


class TestSwitchUrl(LocaleUrlTestCase):
	def test_the_same_page_in_another_language_keeps_the_query_string(self):
		self.open("/products", "category=shirts&sizes=M")

		self.assertEqual(switch_url(language="ar"), "/ar/products?category=shirts&sizes=M")

	def test_switching_to_the_default_language_drops_the_prefix(self):
		self.open("/ar/products/blue-shirt", "colour=red")

		self.assertEqual(switch_url(language="en"), "/products/blue-shirt?colour=red")
		self.open("/ar")
		self.assertEqual(switch_url(language="en"), "/")

	def test_an_explicit_path_and_query(self):
		self.assertEqual(switch_url("/fr/cart", "?discount=A", "ar"), "/ar/cart?discount=A")
		self.assertEqual(
			switch_url("/products", {"sizes": ["S", "M"], "page": None}, "fr"), "/fr/products?sizes=S&sizes=M"
		)
		self.assertEqual(switch_url("/products", None, "fr"), "/fr/products")

	def test_no_language_keeps_the_current_one(self):
		self.open("/fr/products", "page=2")

		self.assertEqual(switch_url(), "/fr/products?page=2")

	def test_a_language_the_shopper_cannot_open_gives_the_default(self):
		self.open("/ar/products")

		self.assertEqual(switch_url(language="de"), "/products")
		self.assertEqual(switch_url(language="xx"), "/products")

	def test_an_off_site_link_stays_off_site(self):
		self.assertEqual(switch_url("//evil.com/x", language="ar"), "//evil.com/x")
		self.assertEqual(switch_url("/\\x", language="ar"), "/\\x")
		self.assertEqual(switch_url("/ar/\\evil.com/x", language="en"), "/evil.com/x")
		self.assertEqual(switch_url("/%2F%2Fx", language="ar"), "/ar/%2F%2Fx")

	def test_the_query_merges_into_the_path_query_before_the_fragment(self):
		self.assertEqual(switch_url("/products#grid", {"page": 2}, "ar"), "/ar/products?page=2#grid")
		self.assertEqual(
			switch_url("/products?page=1&sort=price#grid", {"page": 2}, "ar"),
			"/ar/products?sort=price&page=2#grid",
		)
		self.assertEqual(
			switch_url("/products?page=1&sort=price", "page=3", "fr"), "/fr/products?sort=price&page=3"
		)
		self.assertEqual(
			switch_url("/products?page=1&sort=price", {"page": None}, "fr"), "/fr/products?sort=price"
		)

	def test_the_query_merges_into_the_current_query(self):
		self.open("/products", "page=1&sizes=M")

		self.assertEqual(switch_url(query={"page": 2}, language="ar"), "/ar/products?sizes=M&page=2")

	def test_the_current_query_is_re_encoded(self):
		self.open("/products", MALICIOUS_QUERY)

		link = switch_url(language="ar")

		self.assertTrue(link.startswith("/ar/products?x="), link)
		self.assertFalse(set(link) & set("\"'<> "), link)

	def test_the_current_path_is_percent_encoded(self):
		self.open("/ar/products/blue shirt")

		self.assertEqual(switch_url(language="fr"), "/fr/products/blue%20shirt")


class TestAlternates(LocaleUrlTestCase):
	def test_one_url_per_published_language_default_first(self):
		self.assertEqual(
			alternates("/ar/products/shoe"),
			[
				{"lang": "en", "href": get_url("/products/shoe"), "x_default": True, "locale": "en_US"},
				{"lang": "ar", "href": get_url("/ar/products/shoe"), "x_default": False, "locale": "ar_EG"},
				{"lang": "fr", "href": get_url("/fr/products/shoe"), "x_default": False, "locale": "fr_FR"},
			],
		)

	def test_the_current_page_by_default(self):
		self.open("/fr")

		self.assertEqual(
			[alt["href"] for alt in alternates()], [get_url("/"), get_url("/ar"), get_url("/fr")]
		)

	def test_an_off_site_link_has_none(self):
		self.assertEqual(alternates("//evil.com/x"), [])
		self.assertEqual(alternates("/\\evil.com/x"), [])

	def test_a_single_language_store_has_none(self):
		use_storefront_languages(self, "en", published=("en",), unpublished=("ar",))

		self.assertEqual(alternates("/products/shoe"), [])


class TestSingleLanguageStore(LocaleUrlTestCase):
	def setUp(self):
		super().setUp()
		use_storefront_languages(self, "en", published=("en",))

	def test_urls_carry_no_prefix(self):
		self.open("/products", "sizes=M")

		self.assertEqual(url("/cart"), "/cart")
		self.assertEqual(switch_url(), "/products?sizes=M")

	def test_the_switcher_renders_nothing(self):
		self.assertEqual(frappe.render_template(SWITCHER, {}).strip(), "")


class TestLanguageSwitcher(LocaleUrlTestCase):
	def test_it_links_this_page_in_every_published_language(self):
		self.open("/ar/products", "category=shirts")

		html = frappe.render_template(SWITCHER, {})

		self.assertIn('href="/products?category=shirts" hreflang="en"', html)
		self.assertIn('href="/ar/products?category=shirts" hreflang="ar"', html)
		self.assertIn('href="/fr/products?category=shirts" hreflang="fr"', html)
		self.assertNotIn('hreflang="de"', html)
		self.assertEqual(html.count('aria-current="true"'), 1)
		self.assertIn('hreflang="ar" lang="ar" dir="rtl"', html)

	def test_a_pick_sets_frappes_preferred_language_cookie(self):
		html = frappe.render_template(SWITCHER, {})

		self.assertIn('data-language="fr"', html)
		self.assertIn(
			"document.cookie = 'preferred_language=' + encodeURIComponent(this.dataset.language)", html
		)

	def test_a_query_cannot_break_out_of_the_link(self):
		self.open("/ar/products", MALICIOUS_QUERY)

		html = frappe.render_template(SWITCHER, {})

		self.assertNotIn("<img", html)
		self.assertNotIn('"><', html)
		self.assertEqual(html.count("<a "), 3)

	def test_every_value_in_the_markup_is_escaped(self):
		macro = '{% from "templates/macros/language_switcher.html" import language_switcher %}'
		html = frappe.render_template(
			macro + "{{ language_switcher(link_class=link_class) }}", {"link_class": '"><b>'}
		)

		self.assertNotIn("<b>", html)
		self.assertIn('class="&#34;&gt;&lt;b&gt;', html)
