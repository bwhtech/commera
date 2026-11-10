from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.utils.jinja import get_jenv

from commera.localization import get_country_choices
from commera.localization.markets import delete_cached_rows
from commera.shop_themes.theme_resolver import get_theme_environment
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_localization_urls import MALICIOUS_QUERY, LocaleUrlTestCase
from commera.tests.test_markets import make_market, set_up_markets, use_markets

SWITCHER = (
	'{% from "templates/macros/language_switcher.html" import country_switcher %}'
	"{{ country_switcher(link_class=link_class, current_class=current_class, heading_class=heading_class) }}"
)
STARTER_THEME = Path(__file__).resolve().parents[1] / "themes" / "commera_starter"
STORE_COUNTRY = "India"


class CountrySwitcherTestCase(LocaleUrlTestCase):
	def setUp(self):
		super().setUp()
		set_up_markets(self)
		store_country = patch(
			"commera.localization.country_switcher.get_store_country", return_value=STORE_COUNTRY
		)
		store_country.start()
		self.addCleanup(store_country.stop)

	def choices(self):
		return [
			(group.title, [(country.name, country.url, country.is_current) for country in group.countries])
			for group in get_country_choices()
		]

	def render(self, **classes):
		context = {"link_class": "", "current_class": "", "heading_class": ""} | classes
		return frappe.render_template(SWITCHER, context)  # nosemgrep: frappe-ssti


class TestCountryChoices(CountrySwitcherTestCase):
	def test_countries_are_grouped_by_market_with_the_primary_first(self):
		self.open("/products", "sizes=M")

		self.assertEqual(
			self.choices(),
			[
				(None, [("India", "/products?sizes=M", True)]),
				(
					"Gulf",
					[
						("Saudi Arabia", "/en-sa/products?sizes=M", False),
						("United Arab Emirates", "/en-ae/products?sizes=M", False),
					],
				),
			],
		)

	def test_a_secondary_market_links_back_to_the_primary_and_marks_its_country(self):
		self.open("/ar-sa/products", "page=2")

		self.assertEqual(
			self.choices(),
			[
				(None, [("India", "/ar/products?page=2", False)]),
				(
					"Gulf",
					[
						("Saudi Arabia", "/ar-sa/products?page=2", True),
						("United Arab Emirates", "/ar-ae/products?page=2", False),
					],
				),
			],
		)

	def test_a_language_the_market_lacks_falls_back_to_its_default(self):
		self.open("/fr/cart")

		gulf = get_country_choices()[1]
		self.assertEqual([country.url for country in gulf.countries], ["/ar-sa/cart", "/ar-ae/cart"])

	def test_the_primary_market_is_other_countries_when_a_market_claims_the_store_country(self):
		make_market("India", [STORE_COUNTRY], "en", handle="india")

		self.assertEqual(get_country_choices()[0].countries[0].name, "Other countries")

	def test_disabled_markets_are_not_listed(self):
		self.assertEqual([group.market.handle for group in get_country_choices()], ["primary", "gulf"])

	def test_country_names_are_in_the_page_language(self):
		self.open("/ar-ae/products")
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
		frappe.local.lang = "ar"

		gulf = get_country_choices()[1]
		self.assertEqual(
			[country.name for country in gulf.countries],
			["الإمارات العربية المتحدة", "المملكة العربية السعودية"],
		)


class TestSingleMarketSwitcher(LocaleUrlTestCase):
	def setUp(self):
		super().setUp()
		use_markets(self)

	def test_a_single_market_store_has_no_choices(self):
		self.open("/ar/products")

		self.assertEqual(get_country_choices(), [])
		self.assertEqual(frappe.render_template(SWITCHER, {}).strip(), "")  # nosemgrep: frappe-ssti


class TestCountrySwitcherMacro(CountrySwitcherTestCase):
	def test_it_renders_a_labelled_list_grouped_by_market(self):
		self.open("/en-ae/products", "sizes=M")

		html = self.render(heading_class="heading", current_class="is-current")

		self.assertIn('<ul aria-label="Country"', html)
		self.assertIn('<span aria-hidden="true" class="heading">Gulf</span><ul aria-label="Gulf">', html)
		self.assertIn('<li><a href="/products?sizes=M" class="">India</a></li>', html)
		self.assertIn('href="/en-ae/products?sizes=M" aria-current="true" class=" is-current"', html)
		self.assertEqual(html.count('aria-current="true"'), 1)
		self.assertEqual(html.count("<a "), 3)

	def test_a_query_cannot_break_out_of_the_link(self):
		self.open("/ar-ae/products", MALICIOUS_QUERY)

		html = self.render()

		self.assertNotIn("<img", html)
		self.assertEqual(html.count("<a "), 3)

	def test_every_value_in_the_markup_is_escaped(self):
		frappe.db.set_value("Commera Market", "gulf", "market_name", "<i>Gulf</i>")
		delete_cached_rows()
		frappe.local.request_cache.clear()

		html = self.render(link_class='"><b>')

		self.assertNotIn("<b>", html)
		self.assertNotIn("<i>", html)
		self.assertIn("&lt;i&gt;Gulf&lt;/i&gt;", html)


class TestStarterHeader(CountrySwitcherTestCase):
	def test_the_header_shows_the_country_and_language_picker(self):
		html = render_starter_header()

		self.assertIn('aria-label="Country and language"', html)
		self.assertIn('aria-controls="locale-picker"', html)
		self.assertIn('<ul aria-label="Country"', html)
		self.assertIn('<ul aria-label="Language"', html)

	def test_a_single_market_single_language_store_has_no_picker(self):
		use_markets(self)
		use_storefront_languages(self, "en", published=("en",))

		html = render_starter_header()

		self.assertNotIn("locale-picker", html)
		self.assertNotIn('aria-label="Country"', html)


def render_starter_header():
	environment = get_theme_environment(get_jenv(), [str(STARTER_THEME)])
	section = frappe._dict(settings=frappe._dict(menu="main-menu"))
	commera = frappe._dict(shop=frappe._dict(get_menu=lambda name: None))
	context = {"section": section, "commera": commera, "theme": {}, "shop_name": "Linen House"}
	return environment.get_template("theme://sections/header.html").render(context)
