import os
import shutil
import tempfile
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.website.page_renderers.not_found_page import NotFoundPage
from frappe.website.page_renderers.not_permitted_page import NotPermittedPage
from frappe.website.page_renderers.redirect_page import RedirectPage
from frappe.website.path_resolver import PathResolver, resolve_path
from frappe.website.serve import get_response
from werkzeug.exceptions import HTTPException
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera import seo
from commera.localization import get_localization, get_localized_request, get_request_path
from commera.localization.routing import localize_request
from commera.patches.drop_language_from_theme_routes import execute as drop_language_from_theme_routes
from commera.shop_themes.doctype.shop_theme_settings.shop_theme_settings import (
	DEFAULT_ROUTES,
	build_compiled_routes,
	clear_settings_cache,
)
from commera.shop_themes.route_patterns import has_language_group
from commera.shop_themes.theme_resolver import ThemePageRenderer, match_route
from commera.tests.test_localization import use_storefront_languages

STOREFRONT_API_PATHS = (
	"/api/v2/method/commera.api.storefront.cart.get_cart",
	"/api/method/commera.api.storefront.shop.get_shop",
)


class RoutingTestCase(IntegrationTestCase):
	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		self.addCleanup(setattr, frappe.local, "form_dict", frappe.local.form_dict)
		self.addCleanup(frappe.set_user, frappe.session.user)
		self.addCleanup(frappe.local.flags.pop, "home_page", None)
		self.addCleanup(forget_website_settings)
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
		# frappe.init starts every request with an empty frappe.local.cache.
		frappe.local.cache.pop(frappe.cache.make_key("website_redirects"), None)
		forget_website_settings()
		frappe.local.lang = lang
		frappe.flags.redirect_location = None
		# Frappe's init_request runs the before_request hooks after it has set the language.
		localize_request()

	def assertServes(self, url, endpoint, lang):
		served, renderer = self.open(url)
		self.assertNotIsInstance(renderer, RedirectPage)
		self.assertEqual(served, endpoint)
		self.assertEqual(frappe.local.lang, lang)

	def respond(self, url):
		"""The response frappe.app sends: it returns an HTTPException raised in before_request as is."""
		try:
			self.set_request(url)
		except HTTPException as error:
			return error.get_response()
		return get_response(frappe.local.request.path)

	def assertRedirects(self, url, location):
		response = self.respond(url)
		self.assertEqual(response.status_code, 301)
		self.assertEqual(response.headers["Location"], location)

	def patch_hooks(self, **hooks):
		real_get_hooks = frappe.get_hooks

		def get_hooks(hook=None, *args, **kwargs):
			return hooks[hook] if hook in hooks else real_get_hooks(hook, *args, **kwargs)

		patcher = patch("frappe.get_hooks", side_effect=get_hooks)
		patcher.start()
		self.addCleanup(patcher.stop)


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


# Like a site's own website_redirects or Website Settings redirects.
WEBSITE_REDIRECTS = [
	{"source": "/ar/old", "target": "/ar/new"},
	{"source": "/moved", "target": "/products"},
	{"source": "/to-arabic", "target": "/ar/offers"},
	{"source": "/elsewhere", "target": "https://example.com/"},
]


class TestWebsiteRedirects(RoutingTestCase):
	def setUp(self):
		super().setUp()
		self.patch_hooks(website_redirects=WEBSITE_REDIRECTS)
		frappe.cache.delete_value("website_redirects")
		self.addCleanup(frappe.cache.delete_value, "website_redirects")

	def test_a_rule_written_with_a_prefix_matches_the_prefixed_url(self):
		self.assertRedirects("/ar/old", "/ar/new")

	def test_an_unprefixed_rule_keeps_the_language_of_the_url(self):
		self.assertRedirects("/moved", "/products")
		self.assertRedirects("/ar/moved", "/ar/products")
		self.assertRedirects("/en/moved", "/products")

	def test_a_target_with_its_own_language_or_host_is_kept(self):
		self.assertRedirects("/ar/to-arabic", "/ar/offers")
		self.assertRedirects("/ar/elsewhere", "https://example.com/")


class TestNotPermittedLogin(RoutingTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(setattr, frappe.local, "response", frappe.local.response)
		frappe.local.response = frappe._dict()

	def login_action(self, url):
		self.set_request(url)
		NotPermittedPage(frappe.local.request.path.strip("/")).render()
		return frappe.local.response.context["primary_action"]

	def test_a_guest_returns_to_the_prefixed_page_after_login(self):
		self.assertEqual(
			self.login_action("/ar/account/orders"), "/login?redirect-to=%2Far%2Faccount%2Forders"
		)
		self.assertEqual(self.login_action("/account/orders"), "/login?redirect-to=%2Faccount%2Forders")


PATHS_SEEN_BY_ANOTHER_APP = []


def resolve_like_another_app(path):
	"""A website_path_resolver like Frappe Builder's, which falls back to Frappe's resolve_path."""
	PATHS_SEEN_BY_ANOTHER_APP.append(path)
	return resolve_path(path)


class TestEveryAppRoutesWithoutThePrefix(RoutingTestCase):
	"""Frappe calls every website_path_resolver with the same path and keeps the last endpoint."""

	def in_each_app_order(self):
		commera = "commera.localization.routing.resolve_website_path"
		other = f"{__name__}.resolve_like_another_app"
		for resolvers in ([commera, other], [other, commera]):
			with self.subTest(resolvers=resolvers):
				self.patch_hooks(website_path_resolver=resolvers)
				yield

	def test_a_prefixed_page_is_routed_without_the_prefix(self):
		for _order in self.in_each_app_order():
			self.assertServes("/ar/products/blue-shirt", "/products/details.html", "ar")
			self.assertEqual(PATHS_SEEN_BY_ANOTHER_APP[-1], "products/blue-shirt")

	def test_the_canonical_redirect_wins(self):
		for _order in self.in_each_app_order():
			self.assertRedirects("/en/cart?x=1", "/cart?x=1")

	def test_a_doubled_slash_redirects_before_another_apps_router_sees_it(self):
		for _order in self.in_each_app_order():
			self.assertRedirects("/en/account//orders", "/account/orders")
			self.assertRedirects("/account//orders?x=1", "/account/orders?x=1")
			self.assertRedirects("/ar/account//orders", "/ar/account/orders")

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

	def test_desk_and_other_frappe_namespaces_under_a_prefix_are_not_localized(self):
		urls = (
			"/ar/app",
			"/ar/app/item",
			"/ar/desk",
			"/ar/desk/item",
			"/ar/private/files/x.pdf",
			"/ar/socket.io/x",
			"/ar/assets/x.js",
			"/ar/backups/x",
		)
		with patch("commera.storefront_access.is_storefront_published", return_value=False):
			for url in urls:
				with self.subTest(url):
					_endpoint, renderer = self.open(url, lang="fr")
					self.assertEqual(frappe.local.request.path, url)
					self.assertIsNone(get_localized_request())
					self.assertEqual(frappe.local.lang, "fr")
					self.assertIsInstance(renderer, NotFoundPage)


class TestLangParameter(RoutingTestCase):
	def test_lang_does_not_override_the_url_on_a_storefront_page(self):
		self.open("/products/blue-shirt?_lang=ar", lang="ar")

		self.assertEqual(frappe.local.lang, "en")
		self.assertEqual(get_localization().language.code, "en")

	def test_lang_still_picks_the_language_of_an_api_request(self):
		self.set_request("/api/method/commera.api.ping?_lang=ar")

		self.assertEqual(get_localization().language.code, "ar")

	def test_a_storefront_api_call_without_lang_replies_in_the_default_language(self):
		for path in STOREFRONT_API_PATHS:
			with self.subTest(path):
				# Frappe set Arabic from the cookie, the browser or the user.
				self.set_request(path, lang="ar")
				self.assertEqual(frappe.local.lang, "en")

	def test_a_storefront_api_call_replies_in_its_lang(self):
		self.set_request(f"{STOREFRONT_API_PATHS[0]}?_lang=ar")
		self.assertEqual(frappe.local.lang, "ar")
		self.set_request(f"{STOREFRONT_API_PATHS[0]}?_lang=fr", lang="ar")
		self.assertEqual(frappe.local.lang, "en")

	def test_other_api_calls_keep_frappes_language(self):
		self.set_request("/api/method/commera.api.ping", lang="ar")

		self.assertEqual(frappe.local.lang, "ar")


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


def store_legacy_routes(test_case):
	store_routes(test_case, LEGACY_ROUTES)


def store_routes(test_case, routes, dynamic_pages=False):
	settings = frappe.get_single("Shop Theme Settings")
	settings.set("routes", [])
	settings.dynamic_pages_enabled = int(dynamic_pages)
	for pattern, template_path, requires_auth in routes:
		settings.append(
			"routes",
			{"url_pattern": pattern, "template_path": template_path, "requires_auth": requires_auth},
		)
	settings.save(ignore_permissions=True)
	test_case.addCleanup(clear_settings_cache)
	test_case.addCleanup(frappe.clear_document_cache, "Shop Theme Settings", "Shop Theme Settings")


class TestThemeRoutePatternPatch(IntegrationTestCase):
	def setUp(self):
		store_legacy_routes(self)

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


class ThemeTestCase(RoutingTestCase):
	"""An active theme in a temporary folder, whose every template renders its own path."""

	storefront_published = True

	def setUp(self):
		super().setUp()
		self.theme_dir = tempfile.mkdtemp(prefix="shop_theme_routing_")
		self.addCleanup(shutil.rmtree, self.theme_dir)
		self.patch_theme_context()

	def write_theme_files(self, *relative_paths):
		for relative_path in relative_paths:
			path = os.path.join(self.theme_dir, relative_path)
			os.makedirs(os.path.dirname(path), exist_ok=True)
			with open(path, "w") as theme_file:
				theme_file.write(relative_path)

	def patch_theme_context(self):
		theme_context = {"theme_name": "Routing", "dirs": [self.theme_dir]}
		published = self.storefront_published
		for patcher in (
			patch("commera.shop_themes.theme_resolver.get_render_theme_context", return_value=theme_context),
			patch("commera.storefront_access.is_storefront_published", return_value=published),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def assertThemePage(self, url, template_path):
		_endpoint, renderer = self.open(url)
		self.assertIsInstance(renderer, ThemePageRenderer)
		self.assertEqual(renderer.template_path, template_path)
		return renderer


class TestKeptLegacyThemeRoutes(ThemeTestCase):
	"""A route the patch kept with its language group still serves its old URLs, in its old place."""

	def setUp(self):
		super().setUp()
		store_legacy_routes(self)
		drop_language_from_theme_routes()
		self.write_theme_files(*(template_path for _pattern, template_path, _auth in LEGACY_ROUTES))

	def test_a_kept_route_serves_its_language_urls_before_a_later_custom_route(self):
		renderer = self.assertThemePage("/ar/account/orders", "pages/orders.html")
		self.assertTrue(renderer.requires_auth)
		# Served at /en/account/orders before English moved to the root.
		self.assertThemePage("/account/orders", "pages/orders.html")

	def test_an_earlier_rewritten_route_still_wins_over_a_kept_one(self):
		self.assertThemePage("/ar/lookbook", "pages/lookbook.html")
		self.assertThemePage("/lookbook", "pages/lookbook.html")

	def test_a_kept_route_renders_end_to_end(self):
		frappe.set_user("Administrator")
		response = self.respond("/ar/account/orders")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.get_data(as_text=True), "pages/orders.html")


class TestALanguageGroupInsideAPattern(ThemeTestCase):
	"""Only a leading (?P<lang>…) group is the old language prefix, for the patch and the matcher."""

	PATTERN = r"^collections/(?P<lang>sale|outlet)$"

	def setUp(self):
		super().setUp()
		store_routes(self, [(self.PATTERN, "pages/collection.html", 0)])
		self.write_theme_files("pages/collection.html")

	def test_the_patch_keeps_the_pattern(self):
		drop_language_from_theme_routes()

		self.assertEqual(frappe.get_single("Shop Theme Settings").routes[0].url_pattern, self.PATTERN)
		self.assertFalse(has_language_group(self.PATTERN))
		self.assertTrue(has_language_group(r"^(?P<lang>en|ar)/products$"))

	def test_the_pattern_matches_the_path_as_it_is(self):
		renderer = self.assertThemePage("/collections/sale", "pages/collection.html")
		self.assertEqual(renderer.match["lang"], "sale")
		self.assertEqual(
			self.assertThemePage("/ar/collections/outlet", "pages/collection.html").match["lang"], "outlet"
		)


class TestExcludedPathsUnderAPrefix(ThemeTestCase):
	"""A Frappe namespace under a language prefix is never localized, so no theme page renders there."""

	storefront_published = False

	def setUp(self):
		super().setUp()
		store_routes(self, [(r"^private/catalogue$", "pages/catalogue.html", 0)])
		self.write_theme_files("pages/catalogue.html")

	def test_the_private_store_gate_covers_the_theme_route(self):
		self.assertEqual(self.respond("/private/catalogue").status_code, 503)

	def test_the_theme_does_not_render_the_route_under_a_prefix(self):
		_endpoint, renderer = self.open("/ar/private/catalogue")
		self.assertNotIsInstance(renderer, ThemePageRenderer)

		response = self.respond("/ar/private/catalogue")
		self.assertNotEqual(response.get_data(as_text=True), "pages/catalogue.html")
		self.assertNotEqual(response.status_code, 200)

	def test_the_gate_covers_a_theme_page_at_the_prefixed_path(self):
		store_routes(self, [], dynamic_pages=True)
		self.write_theme_files("pages/ar/private/catalogue.html")

		self.assertEqual(self.respond("/ar/private/catalogue").status_code, 503)


def forget_website_settings():
	"""frappe.init starts every request without them; localize_request may have replaced them."""
	if hasattr(frappe.local, "website_settings"):
		del frappe.local.website_settings
