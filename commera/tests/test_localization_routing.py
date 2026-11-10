from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.website.page_renderers.not_found_page import NotFoundPage
from frappe.website.page_renderers.redirect_page import RedirectPage
from frappe.website.path_resolver import PathResolver, resolve_path
from frappe.website.serve import get_response
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera import seo
from commera.localization import get_localization, get_request_path
from commera.localization.routing import localize_request
from commera.patches.drop_language_from_theme_routes import execute as drop_language_from_theme_routes
from commera.shop_themes.doctype.shop_theme_settings.shop_theme_settings import (
	DEFAULT_ROUTES,
	build_compiled_routes,
	clear_settings_cache,
)
from commera.shop_themes.theme_resolver import match_route
from commera.tests.test_localization import use_storefront_languages


class RoutingTestCase(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		self.addCleanup(frappe.set_user, frappe.session.user)
		self.addCleanup(frappe.local.flags.pop, "home_page", None)
		frappe.set_user("Guest")

	def open(self, url, lang="en", headers=None):
		"""Resolve `url` like a page request that arrives with Frappe's language already set to `lang`."""
		self.set_request(url, lang, headers)
		return PathResolver(frappe.local.request.path).resolve()

	def set_request(self, url, lang="en", headers=None):
		path, _sep, query_string = url.partition("?")
		frappe.local.request = Request(
			EnvironBuilder(path=path, query_string=query_string, headers=headers).get_environ()
		)
		frappe.local.form_dict = frappe._dict(frappe.local.request.args)
		frappe.local.request_cache.clear()
		frappe.local.lang = lang
		frappe.flags.redirect_location = None
		# Frappe's init_request runs the before_request hooks after it has set the language.
		localize_request()

	def assertServes(self, url, endpoint, lang):
		served, renderer = self.open(url)
		self.assertNotIsInstance(renderer, RedirectPage)
		self.assertEqual(served, endpoint)
		self.assertEqual(frappe.local.lang, lang)

	def assertRedirects(self, url, location):
		self.set_request(url)
		response = get_response(frappe.local.request.path)
		self.assertEqual(response.status_code, 301)
		self.assertEqual(response.headers["Location"], location)


class TestRootAndPrefixedRoutes(RoutingTestCase):
	def test_the_default_language_is_served_at_the_root(self):
		self.assertServes("/products/blue-shirt", "/products/details.html", "en")
		self.assertEqual(frappe.form_dict.route, "blue-shirt")
		self.assertServes("/cart", "/cart/cart.html", "en")
		self.assertServes("/account/orders", "/account/orders/index.html", "en")

	def test_another_language_is_served_under_its_prefix(self):
		self.assertServes("/ar/products/blue-shirt", "/products/details.html", "ar")
		self.assertEqual(frappe.form_dict.route, "blue-shirt")
		self.assertServes("/ar/cart/checkout", "/cart/checkout.html", "ar")

	def test_the_home_page_is_the_storefront_for_staff_too(self):
		frappe.set_user("Administrator")
		self.assertServes("/", "index", "en")
		self.assertServes("/ar", "index", "ar")

	def test_a_prefix_is_a_whole_segment_only(self):
		_endpoint, renderer = self.open("/archive", lang="fr")
		self.assertNotIsInstance(renderer, RedirectPage)
		self.assertEqual(frappe.local.lang, "fr")

	def test_an_unpublished_language_is_no_prefix_for_guests(self):
		use_storefront_languages(self, "en", published=("en", "ar"), unpublished=("fr",))
		self.assertServes("/fr/products", "fr/products", "en")

	def test_pages_outside_the_storefront_keep_frappes_language(self):
		for path in ("/commera/orders", "/login", "/me"):
			with self.subTest(path):
				self.open(path, lang="fr")
				self.assertEqual(frappe.local.lang, "fr")


class TestLanguageRedirects(RoutingTestCase):
	def test_the_default_prefix_redirects_to_the_root_keeping_the_query_string(self):
		self.assertRedirects(
			"/en/products/blue-shirt?colour=red&size=M", "/products/blue-shirt?colour=red&size=M"
		)
		self.assertRedirects("/en", "/")
		self.assertRedirects("/EN/cart", "/cart")

	def test_the_redirect_keeps_an_encoded_path_encoded(self):
		self.assertRedirects(
			"/en/cart/Will%20You%20Commit%3F-OS:2?discount=A", "/cart/Will%20You%20Commit%3F-OS:2?discount=A"
		)

	def test_another_default_language_redirects_its_prefix_and_english_takes_en(self):
		use_storefront_languages(self, "ar", published=("ar", "en"))

		self.assertRedirects("/ar/products?sort=new", "/products?sort=new")
		self.assertServes("/products", "/products/list.html", "ar")
		self.assertServes("/en/products", "/products/list.html", "en")

	def test_old_english_links_land_on_the_page_when_english_is_not_published(self):
		use_storefront_languages(self, "ar", published=("ar",))

		self.assertRedirects("/en/products/blue-shirt", "/products/blue-shirt")

	def test_account_redirects_to_the_dashboard_in_the_same_language(self):
		self.assertRedirects("/account", "/account/dashboard")
		self.assertRedirects("/ar/account", "/ar/account/dashboard")
		self.assertRedirects("/en/account", "/account/dashboard")


class TestTheUrlDecidesTheLanguage(RoutingTestCase):
	def test_accept_language_and_the_cookie_never_redirect_or_switch_language(self):
		headers = {"Accept-Language": "ar", "Cookie": "preferred_language=ar"}
		for path in ("/", "/products"):
			with self.subTest(path):
				_endpoint, renderer = self.open(path, lang="ar", headers=headers)
				self.assertNotIsInstance(renderer, RedirectPage)
				self.assertEqual(frappe.local.lang, "en")

	def test_a_logged_in_users_language_does_not_change_the_storefront(self):
		frappe.set_user("Administrator")

		self.open("/products", lang="ar")
		self.assertEqual(frappe.local.lang, "en")
		self.open("/ar/products", lang="en")
		self.assertEqual(frappe.local.lang, "ar")


class TestRedirectsStayOnSite(RoutingTestCase):
	def test_a_path_after_the_prefix_cannot_name_another_host(self):
		for url in ("/en//evil.com", "/en/%2F%2Fevil.com", "/en/\\evil.com", "/en/%5C%5Cevil.com"):
			with self.subTest(url):
				self.assertRedirects(url, "/evil.com")

	def test_an_unprefixed_path_naming_another_host_is_not_redirected(self):
		_endpoint, renderer = self.open("/\\evil.com")
		self.assertNotIsInstance(renderer, RedirectPage)


PATHS_SEEN_BY_ANOTHER_APP = []


def resolve_like_another_app(path):
	"""A website_path_resolver like Frappe Builder's, which falls back to Frappe's resolve_path."""
	PATHS_SEEN_BY_ANOTHER_APP.append(path)
	return resolve_path(path)


class TestEveryAppRoutesWithoutThePrefix(RoutingTestCase):
	"""Frappe calls every website_path_resolver with the same path and keeps the last endpoint."""

	def setUp(self):
		super().setUp()
		self.real_get_hooks = frappe.get_hooks
		patcher = patch("frappe.get_hooks", side_effect=self.get_hooks)
		patcher.start()
		self.addCleanup(patcher.stop)

	def get_hooks(self, hook=None, *args, **kwargs):
		if hook == "website_path_resolver":
			return self.resolvers
		return self.real_get_hooks(hook, *args, **kwargs)

	def in_each_app_order(self):
		commera = "commera.localization.routing.resolve_website_path"
		other = f"{__name__}.resolve_like_another_app"
		for resolvers in ([commera, other], [other, commera]):
			with self.subTest(resolvers=resolvers):
				self.resolvers = resolvers
				yield

	def test_a_prefixed_page_is_routed_without_the_prefix(self):
		for _order in self.in_each_app_order():
			self.assertServes("/ar/products/blue-shirt", "/products/details.html", "ar")
			self.assertEqual(PATHS_SEEN_BY_ANOTHER_APP[-1], "products/blue-shirt")

	def test_the_canonical_redirect_wins(self):
		for _order in self.in_each_app_order():
			self.assertRedirects("/en/cart?x=1", "/cart?x=1")

	def test_the_home_page_is_the_storefront_for_staff(self):
		frappe.set_user("Administrator")
		# get_home_page() reads the before_request override only outside tests.
		with patch.object(frappe, "in_test", False):
			for _order in self.in_each_app_order():
				self.assertServes("/", "index", "en")
				self.assertServes("/ar", "index", "ar")


class TestTheRequestKeepsItsPrefix(RoutingTestCase):
	def test_the_router_sees_the_path_without_the_prefix_and_links_keep_it(self):
		self.set_request("/ar/products/blue-shirt")

		self.assertEqual(frappe.local.request.path, "/products/blue-shirt")
		self.assertEqual(get_request_path(), "/ar/products/blue-shirt")
		self.assertTrue(frappe.local.request.url.endswith("/ar/products/blue-shirt"))
		self.assertTrue(seo.current_request_url().endswith("/ar/products/blue-shirt"))

	def test_other_requests_keep_their_path(self):
		for url in ("/api/method/ping", "/ar/api/method/ping", "/ar/files/x.png", "/commera/orders"):
			with self.subTest(url):
				self.set_request(url)
				self.assertEqual(frappe.local.request.path, url)


class TestLangParameter(RoutingTestCase):
	def test_lang_does_not_override_the_url_on_a_storefront_page(self):
		self.open("/products/blue-shirt?_lang=ar", lang="ar")

		self.assertEqual(frappe.local.lang, "en")
		self.assertEqual(get_localization().language.code, "en")

	def test_lang_still_picks_the_language_of_an_api_request(self):
		self.set_request("/api/method/commera.api.ping?_lang=ar")

		self.assertEqual(get_localization().language.code, "ar")


class TestCachedNotFound(RoutingTestCase):
	def test_a_cached_404_renders_in_the_language_of_the_url(self):
		self.set_request("/ar/no-such-page-anywhere", lang="fr")
		url = frappe.local.request.url
		frappe.cache.hset("website_404", url, True)
		self.addCleanup(frappe.cache.hdel, "website_404", url)

		with patch("frappe.website.path_resolver.can_cache", return_value=True):
			_endpoint, renderer = PathResolver(frappe.local.request.path).resolve()

		self.assertIsInstance(renderer, NotFoundPage)
		self.assertEqual(frappe.local.lang, "ar")
		self.assertIn("/ar/", url)


# (url_pattern, template_path, requires_auth) as stored before the language moved to the root.
LEGACY_ROUTES = [
	(r"^(?P<lang>en|ar)$", "pages/home.html", 0),
	(r"^(?P<lang>en|ar)/products/(?P<route>.+)$", "pages/product.html", 0),
	(r"^(?P<lang>en|ar)/account/orders$", "pages/orders.html", 1),
	(r"^(?P<lang>en|ar|fr)/lookbook$", "pages/lookbook.html", 0),
	(r"^account/orders$", "pages/custom-orders.html", 0),
	(r"^(?P<lang>en|ar|fr)/products/(?P<route>.+)$", "pages/product.html", 0),
	(r"^(?P<lang>en|ar)/lookbook$", "pages/members-lookbook.html", 1),
]


class TestThemeRoutePatternPatch(IntegrationTestCase):
	def setUp(self):
		settings = frappe.get_single("Shop Theme Settings")
		settings.set("routes", [])
		for pattern, template_path, requires_auth in LEGACY_ROUTES:
			settings.append(
				"routes",
				{"url_pattern": pattern, "template_path": template_path, "requires_auth": requires_auth},
			)
		settings.save(ignore_permissions=True)
		self.addCleanup(clear_settings_cache)

	def routes(self):
		return [
			(row.url_pattern, row.template_path, row.requires_auth)
			for row in frappe.get_single("Shop Theme Settings").routes
		]

	def test_patterns_are_rewritten_in_place_and_exact_duplicates_dropped(self):
		drop_language_from_theme_routes()

		self.assertEqual(
			self.routes(),
			[
				(r"^$", "pages/home.html", 0),
				(r"^products/(?P<route>.+)$", "pages/product.html", 0),
				(r"^(?P<lang>en|ar)/account/orders$", "pages/orders.html", 1),
				(r"^lookbook$", "pages/lookbook.html", 0),
				(r"^account/orders$", "pages/custom-orders.html", 0),
				(r"^(?P<lang>en|ar)/lookbook$", "pages/members-lookbook.html", 1),
			],
		)

	def test_a_conflicting_route_is_kept_and_logged(self):
		drop_language_from_theme_routes()

		logged = frappe.get_all(
			"Error Log",
			filters={"method": "Theme route kept with its language group"},
			pluck="error",
		)
		self.assertTrue(any("pages/orders.html" in error for error in logged))
		self.assertTrue(any("pages/members-lookbook.html" in error for error in logged))

	def test_the_patch_runs_twice_without_changes(self):
		drop_language_from_theme_routes()
		first = self.routes()
		drop_language_from_theme_routes()

		self.assertEqual(self.routes(), first)

	def test_rewritten_patterns_match_the_path_without_its_prefix(self):
		drop_language_from_theme_routes()
		routes = build_compiled_routes()["routes"]

		matched, match = match_route(routes, "products/blue-shirt")
		self.assertEqual(matched["template_path"], "pages/product.html")
		self.assertEqual(match["route"], "blue-shirt")
		self.assertEqual(match_route(routes, "")[0]["template_path"], "pages/home.html")
		self.assertEqual(
			match_route(routes, "account/orders")[0]["template_path"], "pages/custom-orders.html"
		)


class TestDefaultThemeRoutes(IntegrationTestCase):
	def test_no_default_route_carries_a_language_group(self):
		for route in DEFAULT_ROUTES:
			with self.subTest(route["url_pattern"]):
				self.assertNotIn("lang", route["url_pattern"])
