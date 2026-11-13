from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_url
from frappe.website.doctype.web_page.web_page import WebPage
from frappe.website.utils import delete_page_cache

from commera import seo
from commera.commera_ecommerce.doctype.commera_market.commera_market import CommeraMarket
from commera.commera_ecommerce.doctype.commera_market_country.commera_market_country import (
	UNIQUE_COUNTRY,
)
from commera.localization import alternates, get_localization, resolve, switch_url, url
from commera.localization.market_setup import MULTI_CURRENCY_FIELD
from commera.localization.markets import (
	StorefrontMarkets,
	delete_cached_rows,
	find_market_by_prefix,
	is_market_language,
)
from commera.localization.urls import get_locale_roots
from commera.migrate import get_private_path_rules
from commera.tests.test_localization import codes, use_storefront_languages
from commera.tests.test_localization_routing import RoutingTestCase
from commera.tests.test_localization_urls import LocaleUrlTestCase
from commera.tests.test_seo import render_seo_head, sitemap_locs

UAE = "United Arab Emirates"


def make_market(
	name,
	countries,
	default_language,
	languages=(),
	enabled=1,
	handle=None,
	sale_price_list=None,
	compare_at_price_list=None,
):
	"""Without price lists, the market sells at the store's sale prices."""
	return frappe.get_doc(
		{
			"doctype": "Commera Market",
			"market_name": name,
			"handle": handle,
			"enabled": enabled,
			"countries": [{"country": country} for country in countries],
			"default_language": default_language,
			"languages": [{"language": language} for language in languages],
			"sale_price_list": sale_price_list or get_store_sale_price_list(),
			"compare_at_price_list": compare_at_price_list,
		}
	).insert(ignore_permissions=True)


def get_store_sale_price_list():
	return frappe.db.get_single_value("Commera Settings", "sale_price_list") or "Standard Selling"


def use_markets(test):
	"""Start the test with no markets and forget them after it. The class rollback runs no hooks.
	ERPNext invoices a market in another currency only with multi-currency invoices on."""
	delete_markets()
	allow_multi_currency_invoices(test)
	test.addCleanup(frappe.local.request_cache.clear)
	test.addCleanup(delete_markets)


def allow_multi_currency_invoices(test, allow=1):
	previous = frappe.db.get_single_value("Accounts Settings", MULTI_CURRENCY_FIELD)
	test.addCleanup(frappe.db.set_single_value, "Accounts Settings", MULTI_CURRENCY_FIELD, previous)
	frappe.db.set_single_value("Accounts Settings", MULTI_CURRENCY_FIELD, allow)


def use_language(test, code):
	"""A Language record for `code`. Frappe ships no script codes such as zh-Hans."""
	if not frappe.db.exists("Language", code):
		language = {"doctype": "Language", "language_code": code, "language_name": code}
		frappe.get_doc(language).insert(ignore_permissions=True)
		test.addCleanup(frappe.db.delete, "Language", code)


def add_saved_language(market, code):
	"""A language row saved before regional languages were refused."""
	frappe.get_doc(
		{
			"doctype": "Commera Market Language",
			"parent": market.name,
			"parenttype": "Commera Market",
			"parentfield": "languages",
			"idx": len(market.languages) + 1,
			"language": code,
		}
	).db_insert()
	delete_cached_rows()


def delete_markets():
	for doctype in ("Commera Market", "Commera Market Country", "Commera Market Language"):
		frappe.db.delete(doctype)
	delete_cached_rows()


def set_up_markets(test):
	"""Gulf: Arabic and English. Benelux is disabled, and German was unpublished after it was added."""
	use_storefront_languages(test, "en", published=("en", "ar", "fr", "de"))
	use_markets(test)
	make_market("Gulf", [UAE, "Saudi Arabia"], "ar", ["en"], handle="gulf")
	make_market("Benelux", ["Belgium", "Netherlands"], "fr", ["en", "de"], enabled=0, handle="benelux")
	use_storefront_languages(test, "en", published=("en", "ar", "fr"), unpublished=("de",))


class TestMarketValidation(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar", "fr"), unpublished=("de",))
		use_markets(self)

	def test_a_country_belongs_to_one_market_only(self):
		make_market("Gulf", [UAE], "ar")

		with self.assertRaisesRegex(frappe.ValidationError, "already in market .*Gulf"):
			make_market("Middle East", ["Saudi Arabia", UAE], "ar")
		with self.assertRaises(frappe.ValidationError):
			make_market("Saudi Arabia", ["Saudi Arabia", "Saudi Arabia"], "ar")

	def test_saving_a_market_again_is_not_a_conflict_with_itself(self):
		market = make_market("Gulf", [UAE], "ar")

		market.append("countries", {"country": "Saudi Arabia"})
		market.save()

	def test_market_languages_must_be_published(self):
		with self.assertRaises(frappe.ValidationError):
			make_market("Germany", ["Germany"], "de")
		with self.assertRaises(frappe.ValidationError):
			make_market("Germany", ["Germany"], "en", ["de"])

	def test_the_default_language_is_one_of_the_market_languages(self):
		market = make_market("Gulf", [UAE], "ar", ["en"])

		self.assertEqual([row.language for row in market.languages], ["en", "ar"])

	def test_the_handle_is_made_from_the_name(self):
		self.assertEqual(make_market("Gulf States", [UAE], "ar").name, "gulf-states")

	def test_the_handle_cannot_name_the_primary_market(self):
		for handle in ("primary", "Gulf", "gulf states"):
			with self.subTest(handle), self.assertRaises(frappe.ValidationError):
				make_market("Gulf", [UAE], "ar", handle=handle)

	def test_a_market_url_cannot_be_a_language_url(self):
		use_storefront_languages(self, "en", published=("en", "pt", "pt-BR"))

		with self.assertRaises(frappe.ValidationError):
			make_market("Brazil", ["Brazil"], "pt")

	def test_a_language_cannot_take_a_market_url(self):
		make_market("Gulf", [UAE], "ar", ["en"])
		settings = frappe.get_doc("Commera Settings")

		settings.append("storefront_languages", {"language": "en-AE", "published": 0})
		with self.assertRaisesRegex(frappe.ValidationError, "/en-ae/.*Gulf"):
			settings.validate_storefront_languages()

		settings.storefront_languages.pop()
		settings.default_storefront_language = "ar-AE"
		with self.assertRaisesRegex(frappe.ValidationError, "/ar-ae/.*Gulf"):
			settings.validate_storefront_languages()

	def test_a_market_language_names_no_region(self):
		use_storefront_languages(self, "en", published=("en", "pt", "pt-BR", "en-US", "zh-TW"))

		for default, languages in (("pt", ["pt-BR"]), ("pt-BR", []), ("en-US", []), ("zh-TW", [])):
			with self.subTest(default=default, languages=languages):
				with self.assertRaisesRegex(frappe.ValidationError, "names a region.*primary market"):
					make_market("Portugal", ["Portugal"], default, languages)

	def test_only_base_and_script_codes_are_market_languages(self):
		for code in ("pt", "fil", "zh-Hans", "sr-latn"):
			self.assertTrue(is_market_language(code), code)
		for code in ("pt-BR", "es-419", "zh-Hans-TW", "en-us", "", None):
			self.assertFalse(is_market_language(code), code)

	def test_a_market_language_may_name_a_script(self):
		use_language(self, "zh-Hans")
		use_storefront_languages(self, "en", published=("en", "zh-Hans"))

		market = make_market("Gulf", [UAE], "zh-Hans")

		self.assertEqual([row.language for row in market.languages], ["zh-Hans"])

	def test_a_script_market_url_cannot_be_a_language_url(self):
		use_language(self, "zh-Hans")
		use_storefront_languages(self, "en", published=("en", "zh-Hans"), unpublished=("zh-Hans-AE",))

		with self.assertRaisesRegex(frappe.ValidationError, "/zh-hans-ae/"):
			make_market("Gulf", [UAE], "zh-Hans")

	def test_a_language_cannot_take_a_script_market_url(self):
		use_language(self, "zh-Hans")
		use_storefront_languages(self, "en", published=("en", "zh-Hans"))
		make_market("Gulf", [UAE], "zh-Hans")
		settings = frappe.get_doc("Commera Settings")

		settings.append("storefront_languages", {"language": "zh-Hans-AE", "published": 0})
		with self.assertRaisesRegex(frappe.ValidationError, "/zh-hans-ae/.*Gulf"):
			settings.validate_storefront_languages()

	def test_a_market_with_a_saved_regional_language_can_drop_it_or_be_disabled(self):
		use_storefront_languages(self, "en", published=("en", "pt", "pt-BR"))
		market = make_market("Portugal", ["Portugal"], "pt")
		add_saved_language(market, "pt-BR")
		market.reload()

		market.enabled = 0
		market.save()
		market.languages = [row for row in market.languages if row.language != "pt-BR"]
		market.save()
		market.append("languages", {"language": "pt-BR"})
		with self.assertRaisesRegex(frappe.ValidationError, "names a region"):
			market.save()

	def test_a_market_save_takes_no_locking_read(self):
		"""Frappe locks the saved market first. A lock shared by every market save made a cycle."""
		market = make_market("Gulf", [UAE], "ar")
		queries = []
		run_sql = frappe.db.sql

		def record(query, *args, **kwargs):
			queries.append(str(query))
			return run_sql(query, *args, **kwargs)

		with patch.object(frappe.db, "sql", side_effect=record):
			make_market("Saudi Arabia", ["Saudi Arabia"], "ar")
			market.append("countries", {"country": "Oman"})
			market.save()
		locks = [query for query in queries if "for update" in query.lower()]

		# Frappe's own lock reads the saved market's rows by parent, never by country.
		self.assertFalse([query for query in locks if "`tabDocType`" in query or "`country`" in query])

	def test_a_country_claimed_during_a_save_gets_the_same_message(self):
		"""The validation read misses a claim made after it. The unique index refuses it."""
		make_market("Gulf", [UAE], "ar", handle="gulf")

		with (
			patch.object(CommeraMarket, "get_countries_in_other_markets", return_value=[]),
			self.assertRaisesRegex(frappe.UniqueValidationError, "already in market .*Gulf"),
		):
			make_market("Emirates", [UAE], "ar")


class TestMarketWithUnpublishedLanguage(IntegrationTestCase):
	"""Gulf took Arabic, its default, while Arabic was published. Arabic was unpublished later."""

	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar", "fr"))
		use_markets(self)
		self.market = make_market("Gulf", [UAE], "ar", ["en"], handle="gulf")
		use_storefront_languages(self, "en", published=("en", "fr"), unpublished=("ar",))

	def test_the_market_can_still_be_renamed_moved_and_disabled(self):
		self.market.market_name = "Gulf States"
		self.market.save()
		self.market.countries[0].country = "Saudi Arabia"
		self.market.append("countries", {"country": "Oman"})
		self.market.save()
		self.assertEqual(StorefrontMarkets.load().find("gulf").default_language.code, "en")
		self.market.enabled = 0
		self.market.save()

		self.assertEqual([row.language for row in self.market.languages], ["en", "ar"])
		self.assertIsNone(StorefrontMarkets.load().find("gulf"))

	def test_the_unpublished_default_can_be_dropped_for_a_published_one(self):
		self.market.default_language = "en"
		self.market.languages = [row for row in self.market.languages if row.language != "ar"]
		self.market.save()

		self.assertEqual([row.language for row in self.market.languages], ["en"])

	def test_the_unpublished_default_is_not_added_back(self):
		self.market.languages = [row for row in self.market.languages if row.language != "ar"]

		with self.assertRaisesRegex(frappe.ValidationError, "Default language .*ar.* is not published"):
			self.market.save()

	def test_an_unpublished_language_cannot_be_chosen_again(self):
		self.market.default_language = "en"
		self.market.save()
		self.market.default_language = "ar"
		with self.assertRaisesRegex(frappe.ValidationError, "Default language .*ar.* is not published"):
			self.market.save()

		self.market.reload()
		self.market.languages = [row for row in self.market.languages if row.language != "ar"]
		self.market.save()
		self.market.append("languages", {"language": "ar"})
		with self.assertRaisesRegex(frappe.ValidationError, "not a published storefront language"):
			self.market.save()


class TestMarketCountryChanges(IntegrationTestCase):
	"""Frappe updates kept rows one by one. A country moving between rows must not trip the unique index."""

	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		use_markets(self)
		self.market = make_market("Gulf", [UAE, "Saudi Arabia", "Oman"], "ar", handle="gulf")
		self.names = [row.name for row in self.market.countries]

	def test_two_rows_can_swap_countries(self):
		first, second, _third = self.market.countries
		first.country, second.country = second.country, first.country
		self.market.save()

		self.assert_saved_countries(["Saudi Arabia", UAE, "Oman"])

	def test_countries_can_move_round_a_chain(self):
		first, second, third = self.market.countries
		first.country, second.country, third.country = "Saudi Arabia", "Oman", UAE
		self.market.save()

		self.assert_saved_countries(["Saudi Arabia", "Oman", UAE])

	def test_rows_can_be_reordered(self):
		self.market.countries.reverse()
		for idx, row in enumerate(self.market.countries, 1):
			row.idx = idx
		self.names.reverse()
		self.market.save()

		self.assert_saved_countries(["Oman", "Saudi Arabia", UAE])

	def test_a_country_of_another_market_is_still_refused(self):
		make_market("Kuwait", ["Kuwait"], "ar", handle="kuwait")
		first, second, _third = self.market.countries
		first.country, second.country = second.country, "Kuwait"

		with self.assertRaisesRegex(frappe.ValidationError, "Kuwait.* is already in market .*Kuwait"):
			self.market.save()

	def test_a_country_claimed_during_a_swap_names_the_other_market(self):
		make_market("Kuwait", ["Kuwait"], "ar", handle="kuwait")
		first, second, _third = self.market.countries
		first.country, second.country = "Kuwait", first.country

		with (
			patch.object(CommeraMarket, "get_countries_in_other_markets", return_value=[]),
			self.assertRaisesRegex(frappe.UniqueValidationError, "already in market .*Kuwait"),
		):
			self.market.save()

	def test_a_clash_inside_the_market_is_named_as_such(self):
		first, second, _third = self.market.countries
		first.country, second.country = second.country, first.country

		with (
			patch.object(CommeraMarket, "reinsert_changed_countries"),
			self.assertRaisesRegex(frappe.UniqueValidationError, "already on another row of this market"),
		):
			self.market.save()

	def assert_saved_countries(self, countries):
		rows = frappe.get_all(
			"Commera Market Country", {"parent": "gulf"}, ["name", "country"], order_by="idx"
		)
		self.assertEqual([row.country for row in rows], countries)
		self.assertEqual([row.name for row in rows], self.names)


class TestMarketCountryIndex(IntegrationTestCase):
	def test_reload_adds_the_unique_country_index(self):
		table = "tabCommera Market Country"
		if frappe.db.has_index(table, UNIQUE_COUNTRY):
			frappe.db.sql_ddl("alter table `tabCommera Market Country` drop index unique_market_country")

		frappe.reload_doc("commera_ecommerce", "doctype", "commera_market_country", force=True)

		self.assertTrue(frappe.db.has_index(table, UNIQUE_COUNTRY))


class TestMarketResolution(IntegrationTestCase):
	def setUp(self):
		set_up_markets(self)

	def test_a_market_prefix_sets_the_market_language_and_country(self):
		localization, path = resolve("/ar-ae/products/linen-shirt")

		self.assertEqual(localization.market.handle, "gulf")
		self.assertEqual(localization.language.code, "ar")
		self.assertEqual(localization.country, "ae")
		self.assertEqual(localization.root_prefix, "/ar-ae")
		self.assertEqual(path, "/products/linen-shirt")

	def test_each_market_language_and_country_has_a_prefix(self):
		for prefix, language, country in (("/en-ae", "en", "ae"), ("/ar-sa", "ar", "sa")):
			with self.subTest(prefix):
				localization, path = resolve(f"{prefix}/cart")
				self.assertEqual(localization.market.handle, "gulf")
				self.assertEqual((localization.language.code, localization.country), (language, country))
				self.assertEqual(path, "/cart")
		self.assertEqual(resolve("/AR-AE/cart")[0].root_prefix, "/ar-ae")

	def test_prefix_codes_name_every_market_prefix(self):
		localization = resolve("/ar-ae/cart")[0]

		self.assertTrue({"ar-ae", "ar-sa", "en-ae", "en-sa", "ar", "en"} <= set(localization.prefix_codes))
		self.assertNotIn("fr-be", localization.prefix_codes)

	def test_only_a_market_language_and_country_is_a_prefix(self):
		for path in ("/fr-ae/cart", "/ar-us/cart", "/ar-aeroplane", "/ar-ae-x/cart", "/-ae/cart"):
			with self.subTest(path):
				localization, rest = resolve(path)
				self.assertTrue(localization.market.is_primary)
				self.assertEqual(rest, path)

	def test_a_disabled_market_resolves_only_for_admins(self):
		self.assertTrue(resolve("/fr-be/products")[0].market.is_primary)

		as_admin, path = resolve("/de-be/products", include_unpublished=True)
		self.assertEqual(as_admin.market.handle, "benelux")
		self.assertEqual(as_admin.language.code, "de")
		self.assertEqual(path, "/products")

	def test_country_picks_the_market_of_an_api_request(self):
		localization = resolve("/api/method/commera.api.cart", country="AE")[0]
		self.assertEqual(localization.market.handle, "gulf")
		self.assertEqual(localization.language.code, "ar")
		self.assertEqual(localization.root_prefix, "/ar-ae")

		self.assertEqual(resolve("/api/method/x", "en", country="sa")[0].root_prefix, "/en-sa")
		self.assertEqual(resolve("/api/method/x", "fr", country="AE")[0].language.code, "ar")

	def test_country_is_a_two_letter_code_or_nothing(self):
		self.assertEqual(resolve("/api/method/x", country="ae")[0].market.handle, "gulf")
		for country in (["AE"], {"code": "AE"}, 971, "ARE", "A1", " ae", "ä"):
			with self.subTest(country):
				localization = resolve("/api/method/x", "fr", country=country)[0]
				self.assertTrue(localization.market.is_primary)
				self.assertIsNone(localization.country)

	def test_a_country_in_no_enabled_market_gets_the_primary_market(self):
		for country in ("US", "BE", "", None, "xx"):
			with self.subTest(country):
				localization = resolve("/api/method/x", "fr", country=country)[0]
				self.assertTrue(localization.market.is_primary)
				self.assertEqual(localization.language.code, "fr")
				self.assertIsNone(localization.country)

	def test_the_url_prefix_wins_over_country(self):
		self.assertTrue(resolve("/ar/cart", country="AE")[0].market.is_primary)
		self.assertEqual(resolve("/en-sa/cart", country="US")[0].market.handle, "gulf")

	def test_localization_lists_the_market_and_available_markets(self):
		localization = resolve("/en-ae/", include_unpublished=True)[0]

		self.assertEqual(codes(localization.available_languages), ["ar", "en"])
		self.assertEqual(localization.default_language.code, "en")
		as_dict = localization.as_dict()
		self.assertEqual(
			as_dict["market"],
			{
				"handle": "gulf",
				"title": "Gulf",
				"is_primary": False,
				"default_language": "ar",
				"languages": ["ar", "en"],
				"countries": ["AE", "SA"],
				"currency": frappe.db.get_value("Price List", get_store_sale_price_list(), "currency"),
			},
		)
		self.assertEqual(as_dict["country"], "AE")
		self.assertEqual([market["handle"] for market in as_dict["available_markets"]], ["primary", "gulf"])

	def test_the_primary_market_is_the_store_itself(self):
		localization = resolve("/fr/products")[0]

		self.assertTrue(localization.market.is_primary)
		self.assertEqual(localization.market.default_language.code, "en")
		self.assertEqual(codes(localization.available_languages), ["en", "ar", "fr"])
		self.assertEqual(localization.root_prefix, "/fr")


class TestSingleMarketStore(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		use_markets(self)

	def test_the_primary_market_is_the_only_market(self):
		localization = resolve("/ar/cart", country="AE")[0]

		self.assertTrue(localization.market.is_primary)
		self.assertEqual([market.handle for market in localization.available_markets], ["primary"])
		self.assertEqual(localization.root_prefix, "/ar")
		self.assertIsNone(localization.country)

	def test_urls_and_alternates_are_unchanged(self):
		self.assertEqual([root.prefix for root in get_locale_roots()], ["", "/ar"])
		self.assertEqual([alt["lang"] for alt in alternates("/cart")], ["en", "ar"])


class TestMarketRequests(RoutingTestCase):
	def setUp(self):
		super().setUp()
		set_up_markets(self)

	def test_a_market_page_is_routed_without_its_prefix(self):
		self.assertServes("/ar-ae/products/blue-shirt", "/products/details.html", "ar")
		self.assertEqual(get_localization().market.handle, "gulf")
		self.assertServes("/en-sa/cart", "/cart/cart.html", "en")
		self.assertEqual(get_localization().country, "sa")

	def test_a_market_prefix_is_never_dropped_for_the_default_language(self):
		self.assertServes("/en-ae", "index", "en")
		self.assertRedirects("/EN-AE/cart?x=1", "/en-ae/cart?x=1")
		self.assertRedirects("/en-ae/account", "/en-ae/account/dashboard")

	def test_a_disabled_market_is_previewed_by_admins_only(self):
		self.open("/fr-be/products")
		self.assertTrue(get_localization().market.is_primary)

		frappe.set_user("Administrator")
		self.assertServes("/fr-be/cart", "/cart/cart.html", "fr")
		self.assertEqual(get_localization().market.handle, "benelux")

	def test_an_untrusted_country_or_lang_falls_back_to_the_primary_market(self):
		for value in (["AE"], {"code": "AE"}, 971, "UAE"):
			with self.subTest(value):
				self.set_request("/api/method/commera.api.ping")
				frappe.local.form_dict = frappe._dict(_country=value, _lang=["ar"])
				localization = get_localization()
				self.assertTrue(localization.market.is_primary)
				self.assertEqual(localization.language.code, "en")

	def test_an_omitted_lang_is_the_market_default_language(self):
		"""The request contract: a page sends `_lang` only when it is not its market's default."""
		self.set_request("/api/method/commera.api.ping?_lang=en&_country=AE")
		self.assertEqual((get_localization().language.code, get_localization().root_prefix), ("en", "/en-ae"))

		self.set_request("/api/method/commera.api.ping?_country=AE")
		self.assertEqual((get_localization().language.code, get_localization().root_prefix), ("ar", "/ar-ae"))

		self.set_request("/api/method/commera.api.ping")
		self.assertTrue(get_localization().market.is_primary)
		self.assertEqual(get_localization().language.code, "en")

	def test_country_picks_the_market_of_an_api_request_only(self):
		self.set_request("/api/method/commera.api.ping?_country=AE&_lang=en")
		self.assertEqual(get_localization().market.handle, "gulf")
		self.assertEqual(get_localization().root_prefix, "/en-ae")

		self.open("/products?_country=AE")
		self.assertTrue(get_localization().market.is_primary)


class TestMarketPageCache(RoutingTestCase):
	"""Frappe caches a page by its unprefixed path and language. Two countries share English."""

	ROUTE = "market-cache-check"

	def setUp(self):
		super().setUp()
		set_up_markets(self)
		# The class rollback runs after the last test only.
		frappe.db.delete("Web Page", {"route": self.ROUTE})
		frappe.get_doc(
			{
				"doctype": "Web Page",
				"title": "Market Cache Check",
				"route": self.ROUTE,
				"published": 1,
				"content_type": "HTML",
				"main_section_html": "<!-- static --><p>Shop {{ root_prefix }}/cart</p>",
				"dynamic_template": 1,
			}
		).insert(ignore_permissions=True)
		render_dynamic = patch.object(WebPage, "render_dynamic", render_with_root_prefix)
		render_dynamic.start()
		self.addCleanup(render_dynamic.stop)
		conf = patch.dict(frappe.conf, {"developer_mode": 0, "disable_website_cache": 0})
		conf.start()
		self.addCleanup(conf.stop)
		delete_page_cache(self.ROUTE)
		self.addCleanup(delete_page_cache, self.ROUTE)

	def render(self, path):
		frappe.local.response = frappe._dict(docs=[])
		response = self.respond(path)
		self.assertEqual(response.status_code, 200)
		return response

	def test_each_market_url_renders_its_own_page(self):
		for prefix in ("/en-sa", "/en-ae", "/en-sa"):
			with self.subTest(prefix):
				response = self.render(f"{prefix}/{self.ROUTE}")
				self.assertIn(f"Shop {prefix}/cart", response.get_data(as_text=True))
				self.assertEqual(response.headers["X-From-Cache"], "False")

	def test_the_primary_market_is_still_cached(self):
		self.render(f"/{self.ROUTE}")
		response = self.render(f"/{self.ROUTE}")

		self.assertIn("Shop /cart", response.get_data(as_text=True))
		self.assertEqual(response.headers["X-From-Cache"], "True")


def render_with_root_prefix(page, context, render=WebPage.render_dynamic):
	"""A page that shows its market. Restricted Web Page templates cannot call url()."""
	context.root_prefix = get_localization().root_prefix
	return render(page, context)


class TestMarketUrls(LocaleUrlTestCase):
	def setUp(self):
		super().setUp()
		set_up_markets(self)

	def test_url_keeps_the_market_prefix(self):
		self.open("/ar-ae/products")

		self.assertEqual(url("/cart"), "/ar-ae/cart")
		self.assertEqual(url("/en-sa/page/about"), "/ar-ae/page/about")
		self.assertEqual(url("/fr/page/about"), "/ar-ae/page/about")
		self.assertEqual(url("/"), "/ar-ae")

	def test_switch_url_moves_to_a_market_and_keeps_the_query(self):
		self.open("/products", "sizes=M&page=2")

		self.assertEqual(switch_url(market="gulf"), "/en-ae/products?sizes=M&page=2")
		self.assertEqual(switch_url(market="gulf", language="ar"), "/ar-ae/products?sizes=M&page=2")
		self.assertEqual(switch_url(country="SA", query={"page": None}), "/en-sa/products?sizes=M")
		self.assertEqual(switch_url("/cart?x=1", "y=2", "ar", "gulf"), "/ar-ae/cart?x=1&y=2")

	def test_switch_url_falls_back_to_the_market_default_language(self):
		self.open("/fr/products")

		self.assertEqual(switch_url(market="gulf"), "/ar-ae/products")
		self.assertEqual(switch_url(market="gulf", language="fr"), "/ar-ae/products")

	def test_switch_url_back_to_the_primary_market(self):
		self.open("/ar-sa/products", "page=2")

		self.assertEqual(switch_url(market="primary"), "/ar/products?page=2")
		self.assertEqual(switch_url(market="primary", language="en"), "/products?page=2")
		self.assertEqual(switch_url(country="US"), "/ar/products?page=2")
		self.assertEqual(switch_url(language="en"), "/en-sa/products?page=2")
		self.assertEqual(switch_url(market="nowhere"), "/ar/products?page=2")

	def test_a_disabled_market_is_no_switch_target_for_guests(self):
		self.assertEqual(switch_url("/products", market="benelux"), "/products")
		self.assertEqual(switch_url("/products", country="BE"), "/products")

	def test_switch_url_keeps_links_on_site(self):
		self.assertEqual(switch_url("//evil.com/x", market="gulf"), "//evil.com/x")
		self.assertEqual(switch_url("/ar-ae/\\evil.com/x", market="primary"), "/evil.com/x")
		self.assertEqual(switch_url("/en-ae//evil.com/x", market="gulf"), "/en-ae/evil.com/x")

	def test_alternates_include_every_enabled_market_url(self):
		self.assertEqual(
			alternates("/ar-ae/products/shoe"),
			[
				{"lang": "en", "href": get_url("/products/shoe"), "x_default": True, "locale": "en_US"},
				{"lang": "ar", "href": get_url("/ar/products/shoe"), "x_default": False, "locale": "ar_EG"},
				{"lang": "fr", "href": get_url("/fr/products/shoe"), "x_default": False, "locale": "fr_FR"},
				{
					"lang": "ar-AE",
					"href": get_url("/ar-ae/products/shoe"),
					"x_default": False,
					"locale": "ar_AE",
				},
				{
					"lang": "ar-SA",
					"href": get_url("/ar-sa/products/shoe"),
					"x_default": False,
					"locale": "ar_SA",
				},
				{
					"lang": "en-AE",
					"href": get_url("/en-ae/products/shoe"),
					"x_default": False,
					"locale": "en_AE",
				},
				{
					"lang": "en-SA",
					"href": get_url("/en-sa/products/shoe"),
					"x_default": False,
					"locale": "en_SA",
				},
			],
		)

	def test_a_market_page_head_lists_every_locale_url(self):
		self.open("/ar-ae/products/shoe")
		page_seo = seo.build_page_seo({})
		hreflangs = [alt["lang"] for alt in page_seo["alternates"]]
		self.assertEqual(hreflangs, ["en", "ar", "fr", "ar-AE", "ar-SA", "en-AE", "en-SA"])

		html = render_seo_head(page_seo)

		self.assertIn(f'hreflang="ar-AE" href="{get_url("/ar-ae/products/shoe")}"', html)
		self.assertIn(f'hreflang="x-default" href="{get_url("/products/shoe")}"', html)
		self.assertIn('<meta property="og:locale" content="ar_AE">', html)
		for locale in ("en_US", "ar_EG", "fr_FR", "ar_SA", "en_AE", "en_SA"):
			self.assertIn(f'<meta property="og:locale:alternate" content="{locale}">', html)
		self.assertNotIn('og:locale:alternate" content="ar_AE"', html)

	def test_the_sitemap_and_robots_include_market_urls(self):
		locs = sitemap_locs("pages", 1)
		for prefix in ("/ar", "/fr", "/ar-ae", "/ar-sa", "/en-ae", "/en-sa"):
			self.assertIn(get_url(prefix), locs)
		self.assertIn(get_url("/"), locs)
		self.assertNotIn(get_url("/fr-be"), locs)

		rules = get_private_path_rules()
		self.assertIn("Disallow: /cart\n", rules)
		self.assertIn("Disallow: /en-ae/cart\n", rules)
		self.assertNotIn("/de-be/", rules)

	def test_a_script_language_has_a_market_url_and_hreflang(self):
		use_language(self, "zh-Hans")
		use_storefront_languages(self, "en", published=("en", "ar", "zh-Hans"))
		make_market("Singapore", ["Singapore"], "zh-Hans", handle="sg")

		localization, path = resolve("/zh-hans-sg/products")
		self.assertEqual((localization.market.handle, localization.language.code), ("sg", "zh-Hans"))
		self.assertEqual(path, "/products")
		self.open("/zh-hans-sg/products")
		self.assertEqual(url("/cart"), "/zh-hans-sg/cart")
		self.assertIn(
			{
				"lang": "zh-Hans-SG",
				"href": get_url("/zh-hans-sg/cart"),
				"x_default": False,
				"locale": "zh_SG",
			},
			alternates("/cart"),
		)

	def test_traditional_and_simplified_chinese_get_their_own_og_locale(self):
		for code in ("zh-Hant", "zh-Hans"):
			use_language(self, code)
		use_storefront_languages(self, "en", published=("en", "zh-Hant", "zh-Hans"))
		self.open("/zh-hant/products/shoe")

		html = render_seo_head(seo.build_page_seo({}))

		self.assertIn('<meta property="og:locale" content="zh_TW">', html)
		self.assertIn('<meta property="og:locale:alternate" content="zh_CN">', html)
		locales = {alt["lang"]: alt["locale"] for alt in alternates()}
		self.assertEqual((locales["zh-Hant"], locales["zh-Hans"]), ("zh_TW", "zh_CN"))

	def test_a_saved_regional_market_language_gets_no_url(self):
		use_storefront_languages(self, "en", published=("en", "ar", "en-GB"))
		add_saved_language(frappe.get_doc("Commera Market", "gulf"), "en-GB")

		self.assertEqual(codes(StorefrontMarkets.load().find("gulf").languages), ["ar", "en"])
		self.assertFalse([alt for alt in alternates("/cart") if "-gb-" in alt["href"].lower()])
		self.assertNotIn("en-GB-AE", [alt["lang"] for alt in alternates("/cart")])
		self.assertIsNone(find_market_by_prefix("en-gb-ae"))

	def test_a_single_language_store_with_a_market_has_alternates(self):
		use_storefront_languages(self, "en", published=("en",))
		delete_cached_rows()

		self.assertEqual([alt["lang"] for alt in alternates("/cart")], ["en", "en-AE", "en-SA"])
