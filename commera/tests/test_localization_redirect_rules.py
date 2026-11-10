from unittest.mock import patch

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
		# Stored as before this release: saving now rewrites /en/ targets.
		settings.flags.ignore_validate = True
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


QUERY_AWARE_HOOK = {"source": "/elsewhere", "target": "/there", "match_with_query_string": True}


class TestRedirectRuleTargets(RedirectRulesTestCase):
	def save_rules(self, *rules):
		frappe.set_user("Administrator")
		settings = frappe.get_single("Website Settings")
		settings.set("route_redirects", [])
		for rule in rules:
			settings.append("route_redirects", rule)
		settings.save(ignore_permissions=True)
		clear_redirect_caches()
		frappe.set_user("Guest")
		return [row.target for row in frappe.get_single("Website Settings").route_redirects]

	def with_query_aware_hook(self):
		"""Any such hook makes Frappe skip its redirect cache whenever the URL has a query string."""
		get_hooks = frappe.get_hooks

		def hooks_with_query_aware_rule(hook=None, *args, **kwargs):
			hooks = get_hooks(hook, *args, **kwargs)
			return [*hooks, QUERY_AWARE_HOOK] if hook == "website_redirects" else hooks

		return patch.object(frappe, "get_hooks", hooks_with_query_aware_rule)

	def test_saving_rules_moves_targets_off_the_default_prefix_and_keeps_every_rule(self):
		targets = self.save_rules(
			LEGACY_RULE,
			{"source": "/products/[ab]", "target": "/en/products/[ab]"},
			{"source": "/sale", "target": "https://example.com/en/sale"},
		)

		self.assertEqual(targets, [r"/products/\1", "/products/[ab]", "https://example.com/en/sale"])

	def test_a_query_aware_hook_elsewhere_cannot_loop_a_rule_to_its_own_page(self):
		self.save_rules(
			LEGACY_RULE,
			{"source": r"/shoes/(.*)\.html", "target": r"/en/shoes/\1.html"},
			{"source": "/boots/(?P<slug>.*)", "target": r"/en/boots/\g<slug>"},
		)

		with self.with_query_aware_hook():
			for url in ("/products/shoe?colour=red", "/shoes/a.html?x=1", "/boots/b?x=1"):
				with self.subTest(url):
					self.assertEqual(self.follow(url), [])
			self.assertEqual(self.follow("/en/products/shoe?colour=red"), ["/products/shoe?colour=red"])

	def test_a_rule_that_only_adds_a_query_string_redirects_once(self):
		self.store_rules({"source": "/products", "target": "/products?category=sale"})

		self.assertEqual(self.follow("/products"), ["/products?category=sale"])
		self.assertEqual(self.follow("/products?category=sale"), [])
		with self.with_query_aware_hook():
			self.assertEqual(self.follow("/products?category=sale"), [])


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
