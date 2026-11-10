import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_url

from commera import seo
from commera.localization import alternates, get_localization, resolve, switch_url, url
from commera.localization.markets import delete_cached_rows
from commera.migrate import get_private_path_rules
from commera.tests.test_localization import codes, use_storefront_languages
from commera.tests.test_localization_routing import RoutingTestCase
from commera.tests.test_localization_urls import LocaleUrlTestCase
from commera.www.sitemap_segment import get_language_prefixes

UAE = "United Arab Emirates"


def make_market(name, countries, default_language, languages=(), enabled=1, handle=None):
	return frappe.get_doc(
		{
			"doctype": "Commera Market",
			"market_name": name,
			"handle": handle,
			"enabled": enabled,
			"countries": [{"country": country} for country in countries],
			"default_language": default_language,
			"languages": [{"language": language} for language in languages],
		}
	).insert(ignore_permissions=True)


def use_markets(test):
	"""Start the test with no markets and forget them after it. The class rollback runs no hooks."""
	delete_markets()
	test.addCleanup(frappe.local.request_cache.clear)
	test.addCleanup(delete_markets)


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

		with self.assertRaises(frappe.ValidationError):
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

	def test_only_a_market_language_and_country_is_a_prefix(self):
		for path in ("/fr-ae/cart", "/ar-us/cart", "/ar-aeroplane", "/ar-ae-x/cart", "/-ae/cart"):
			with self.subTest(path):
				localization, rest = resolve(path)
				self.assertTrue(localization.market.primary)
				self.assertEqual(rest, path)

	def test_a_disabled_market_resolves_only_for_admins(self):
		self.assertTrue(resolve("/fr-be/products")[0].market.primary)

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

	def test_a_country_in_no_enabled_market_gets_the_primary_market(self):
		for country in ("US", "BE", "", None, "xx"):
			with self.subTest(country):
				localization = resolve("/api/method/x", "fr", country=country)[0]
				self.assertTrue(localization.market.primary)
				self.assertEqual(localization.language.code, "fr")
				self.assertIsNone(localization.country)

	def test_the_url_prefix_wins_over_country(self):
		self.assertTrue(resolve("/ar/cart", country="AE")[0].market.primary)
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
				"primary": False,
				"default_language": "ar",
				"languages": ["ar", "en"],
				"countries": ["AE", "SA"],
			},
		)
		self.assertEqual(as_dict["country"], "AE")
		self.assertEqual([market["handle"] for market in as_dict["available_markets"]], ["primary", "gulf"])

	def test_the_primary_market_is_the_store_itself(self):
		localization = resolve("/fr/products")[0]

		self.assertTrue(localization.market.primary)
		self.assertEqual(localization.market.default_language.code, "en")
		self.assertEqual(codes(localization.available_languages), ["en", "ar", "fr"])
		self.assertEqual(localization.root_prefix, "/fr")


class TestSingleMarketStore(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		use_markets(self)

	def test_the_primary_market_is_the_only_market(self):
		localization = resolve("/ar/cart", country="AE")[0]

		self.assertTrue(localization.market.primary)
		self.assertEqual([market.handle for market in localization.available_markets], ["primary"])
		self.assertEqual(localization.root_prefix, "/ar")
		self.assertIsNone(localization.country)

	def test_urls_and_alternates_are_unchanged(self):
		self.assertEqual(get_language_prefixes(), ["", "/ar"])
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
		self.assertTrue(get_localization().market.primary)

		frappe.set_user("Administrator")
		self.assertServes("/fr-be/cart", "/cart/cart.html", "fr")
		self.assertEqual(get_localization().market.handle, "benelux")

	def test_country_picks_the_market_of_an_api_request_only(self):
		self.set_request("/api/method/commera.api.ping?_country=AE&_lang=en")
		self.assertEqual(get_localization().market.handle, "gulf")
		self.assertEqual(get_localization().root_prefix, "/en-ae")

		self.open("/products?_country=AE")
		self.assertTrue(get_localization().market.primary)


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
				{"lang": "en", "href": get_url("/products/shoe"), "x_default": True},
				{"lang": "ar", "href": get_url("/ar/products/shoe"), "x_default": False},
				{"lang": "fr", "href": get_url("/fr/products/shoe"), "x_default": False},
				{"lang": "ar-AE", "href": get_url("/ar-ae/products/shoe"), "x_default": False},
				{"lang": "ar-SA", "href": get_url("/ar-sa/products/shoe"), "x_default": False},
				{"lang": "en-AE", "href": get_url("/en-ae/products/shoe"), "x_default": False},
				{"lang": "en-SA", "href": get_url("/en-sa/products/shoe"), "x_default": False},
			],
		)

	def test_seo_sitemap_and_robots_include_market_urls(self):
		hreflangs = [alt["lang"] for alt in seo.build_alternates("/en-ae/")]
		self.assertEqual(hreflangs, ["en", "ar", "fr", "ar-AE", "ar-SA", "en-AE", "en-SA"])
		self.assertIn("/ar-sa", get_language_prefixes())
		self.assertNotIn("/fr-be", get_language_prefixes())
		rules = get_private_path_rules()
		self.assertIn("Disallow: /en-ae/cart\n", rules)
		self.assertNotIn("/de-be/", rules)

	def test_a_single_language_store_with_a_market_has_alternates(self):
		use_storefront_languages(self, "en", published=("en",))
		delete_cached_rows()

		self.assertEqual([alt["lang"] for alt in alternates("/cart")], ["en", "en-AE", "en-SA"])
