import frappe
from frappe.tests import IntegrationTestCase
from frappe.website.page_renderers.redirect_page import RedirectPage
from frappe.website.path_resolver import PathResolver
from frappe.website.serve import get_response
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

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


LEGACY_PATTERNS = [
	r"^(?P<lang>en|ar)$",
	r"^(?P<lang>en|ar)/products/(?P<route>.+)$",
	r"^(?P<lang>en|ar)/account/orders$",
	r"^(?P<lang>en|ar|fr)/lookbook$",
	r"^account/orders$",
]


class TestThemeRoutePatternPatch(IntegrationTestCase):
	def setUp(self):
		settings = frappe.get_single("Shop Theme Settings")
		settings.set("routes", [])
		for idx, pattern in enumerate(LEGACY_PATTERNS):
			settings.append(
				"routes",
				{"url_pattern": pattern, "template_path": f"pages/p{idx}.html", "requires_auth": idx == 2},
			)
		settings.save(ignore_permissions=True)
		self.addCleanup(clear_settings_cache)

	def routes(self):
		return [
			(row.url_pattern, row.template_path, row.requires_auth)
			for row in frappe.get_single("Shop Theme Settings").routes
		]

	def test_patterns_are_rewritten_in_place_without_duplicates(self):
		drop_language_from_theme_routes()

		self.assertEqual(
			self.routes(),
			[
				(r"^$", "pages/p0.html", 0),
				(r"^products/(?P<route>.+)$", "pages/p1.html", 0),
				(r"^account/orders$", "pages/p2.html", 1),
				(r"^lookbook$", "pages/p3.html", 0),
			],
		)

	def test_the_patch_runs_twice_without_changes(self):
		drop_language_from_theme_routes()
		first = self.routes()
		drop_language_from_theme_routes()

		self.assertEqual(self.routes(), first)

	def test_rewritten_patterns_match_the_path_without_its_prefix(self):
		drop_language_from_theme_routes()
		routes = build_compiled_routes()["routes"]

		matched, match = match_route(routes, "products/blue-shirt")
		self.assertEqual(matched["template_path"], "pages/p1.html")
		self.assertEqual(match["route"], "blue-shirt")
		self.assertEqual(match_route(routes, "")[0]["template_path"], "pages/p0.html")


class TestDefaultThemeRoutes(IntegrationTestCase):
	def test_no_default_route_carries_a_language_group(self):
		for route in DEFAULT_ROUTES:
			with self.subTest(route["url_pattern"]):
				self.assertNotIn("lang", route["url_pattern"])
