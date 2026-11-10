import frappe

from commera.patches.drop_default_language_from_redirect_targets import (
	execute as drop_default_language_from_redirect_targets,
)
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_localization_routing import RoutingTestCase

MAX_HOPS = 5

# A rule from before the default language moved to the root.
LEGACY_RULE = {"source": "/products/(.*)", "target": r"/en/products/\1"}


class RedirectRulesTestCase(RoutingTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(clear_redirect_caches)

	def store_rules(self, *rules):
		frappe.set_user("Administrator")
		settings = frappe.get_single("Website Settings")
		settings.set("route_redirects", [])
		for rule in rules:
			settings.append("route_redirects", rule)
		settings.save(ignore_permissions=True)
		clear_redirect_caches()
		frappe.set_user("Guest")

	def follow(self, url):
		"""The Location of every redirect from `url` until a page answers. Fails on a loop."""
		hops = []
		for _hop in range(MAX_HOPS):
			response = self.respond(url)
			if response.status_code not in (301, 302):
				return hops
			url = response.headers["Location"]
			hops.append(url)
		self.fail(f"{hops[0]} does not stop redirecting: {hops}")


class TestLegacyDefaultPrefixRules(RedirectRulesTestCase):
	def setUp(self):
		super().setUp()
		self.store_rules(LEGACY_RULE)

	def test_the_page_at_the_root_is_served(self):
		self.assertEqual(self.follow("/products/shoe"), [])

	def test_the_old_url_redirects_once_and_stops(self):
		self.assertEqual(self.follow("/en/products/shoe"), ["/products/shoe"])

	def test_another_language_is_not_sent_to_the_default_one(self):
		self.assertEqual(self.follow("/ar/products/shoe"), [])

	def test_a_rule_to_another_page_still_redirects(self):
		self.store_rules({"source": "/products/old-shoe", "target": "/en/products/shoe"}, LEGACY_RULE)

		self.assertEqual(self.follow("/products/old-shoe"), ["/products/shoe"])
		self.assertEqual(self.follow("/ar/products/old-shoe"), ["/ar/products/shoe"])

	def test_a_page_outside_the_storefront_follows_frappes_rule_to_the_end(self):
		self.store_rules({"source": "/old-shoe", "target": "/en/products/shoe"}, LEGACY_RULE)

		self.assertEqual(self.follow("/old-shoe"), ["/en/products/shoe", "/products/shoe"])

	def test_english_keeps_its_prefix_when_it_is_not_the_default(self):
		use_storefront_languages(self, "ar", published=("ar", "en"))

		self.assertEqual(self.follow("/products/shoe"), ["/en/products/shoe"])
		self.assertEqual(self.follow("/en/products/shoe"), [])


class TestRedirectTargetPatch(RedirectRulesTestCase):
	def targets(self):
		return [row.target for row in frappe.get_single("Website Settings").route_redirects]

	def test_targets_under_the_default_prefix_move_to_the_root(self):
		self.store_rules(
			LEGACY_RULE,
			{"source": "/home", "target": "/en"},
			{"source": "/offers", "target": "/en/page/offers?from=home"},
			{"source": "/arabic", "target": "/ar/products"},
			{"source": "/away", "target": "https://example.com/en/x"},
		)
		drop_default_language_from_redirect_targets()
		frappe.clear_document_cache("Website Settings", "Website Settings")

		self.assertEqual(
			self.targets(),
			[r"/products/\1", "/", "/page/offers?from=home", "/ar/products", "https://example.com/en/x"],
		)

	def test_english_targets_stay_when_english_is_not_the_default(self):
		use_storefront_languages(self, "ar", published=("ar", "en"))
		self.store_rules(LEGACY_RULE)
		drop_default_language_from_redirect_targets()
		frappe.clear_document_cache("Website Settings", "Website Settings")

		self.assertEqual(self.targets(), [LEGACY_RULE["target"]])


def clear_redirect_caches():
	frappe.clear_document_cache("Website Settings", "Website Settings")
	frappe.cache.delete_value("website_redirects")
	if hasattr(frappe.local, "website_settings"):
		del frappe.local.website_settings
