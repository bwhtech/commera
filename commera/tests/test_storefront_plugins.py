# Copyright (c) 2026, company@bwhstudios.com and contributors

import frappe
from frappe.deferred_insert import save_to_db
from frappe.tests import IntegrationTestCase
from frappe.utils import get_html_for_route, set_request

from commera import storefront_plugins

BANNER = "commera/tests/storefront_plugin_templates/banner.html"
BROKEN = "commera/tests/storefront_plugin_templates/broken.html"
SCRIPT = "/assets/commera/js/test-plugin.js"
STYLE = "/assets/commera/css/test-plugin.css"


class TestStorefrontPlugins(IntegrationTestCase):
	def setUp(self):
		self.previous_request = getattr(frappe.local, "request", None)
		frappe.db.delete("Commera Storefront App")
		save_to_db()
		frappe.db.delete("Error Log")
		frappe.clear_document_cache("Commera Settings", "Commera Settings")
		storefront_plugins.clear_storefront_plugin_cache()

	def tearDown(self):
		frappe.local.request = self.previous_request
		storefront_plugins.clear_storefront_plugin_cache()

	def declare_hooks(self, hooks):
		self.enterContext(self.patch_hooks(hooks))
		storefront_plugins.sync_storefront_apps()

	def set_enabled(self, enabled):
		settings = frappe.get_single("Commera Settings")
		for row in settings.storefront_apps:
			if row.app == "commera":
				row.enabled = enabled
		settings.save()

	def get_error_titles(self):
		save_to_db()
		return frappe.get_all("Error Log", pluck="method")

	def declare_full_plugin(self):
		self.declare_hooks(
			{
				"commera_storefront_include_js": [SCRIPT],
				"commera_storefront_include_css": [STYLE],
				"commera_storefront_blocks": {
					"cart_banner": [BANNER],
					"checkout_banner": [BANNER],
					"page_overlay": [BANNER],
				},
			}
		)

	def test_declaring_app_is_listed_switched_off(self):
		self.declare_full_plugin()

		rows = frappe.get_single("Commera Settings").storefront_apps
		self.assertIn(("commera", 0), [(row.app, row.enabled) for row in rows])

	def test_switching_on_renders_tags_and_blocks(self):
		self.declare_full_plugin()
		self.assertEqual(storefront_plugins.format_plugin_includes("js"), "")

		self.set_enabled(1)

		self.assertEqual(
			storefront_plugins.format_plugin_includes("css"), f'<link rel="stylesheet" href="{STYLE}">'
		)
		self.assertEqual(
			storefront_plugins.format_plugin_includes("js"), f'<script defer src="{SCRIPT}"></script>'
		)
		banner = storefront_plugins.plugin_slot("cart_banner")
		store_name = frappe.db.get_single_value("Commera Settings", "store_name")
		currency = frappe.db.get_single_value("Global Defaults", "default_currency")
		self.assertIn(f"{store_name}|{currency}|{frappe.local.lang}|False", banner)

	def test_asset_outside_the_app_is_refused(self):
		self.declare_hooks(
			{
				"commera_storefront_include_js": ["/assets/frappe/js/frappe-web.bundle.js", SCRIPT],
				"commera_storefront_include_css": ["/assets/commera/../frappe/css/website.css"],
			}
		)
		self.set_enabled(1)

		self.assertEqual(
			storefront_plugins.format_plugin_includes("js"), f'<script defer src="{SCRIPT}"></script>'
		)
		self.assertEqual(storefront_plugins.format_plugin_includes("css"), "")
		self.assertEqual(self.get_error_titles().count("commera: storefront include refused"), 2)

	def test_template_outside_the_app_is_refused(self):
		self.declare_hooks(
			{
				"commera_storefront_blocks": {
					"cart_banner": [
						"frappe/templates/includes/footer/footer.html",
						"commera/../frappe/templates/includes/footer/footer.html",
						"commera/tests/storefront_plugin_templates/missing.html",
						BANNER,
					]
				}
			}
		)
		self.set_enabled(1)

		self.assertEqual(storefront_plugins.plugin_slot("cart_banner").count("test-plugin-banner"), 1)
		self.assertEqual(self.get_error_titles().count("commera: storefront block refused"), 3)

	def test_unknown_slot_is_skipped(self):
		self.declare_hooks(
			{"commera_storefront_blocks": {"cart_line_badge": [BANNER], "cart_banner": [BANNER]}}
		)
		self.set_enabled(1)

		self.assertEqual(storefront_plugins.plugin_slot("cart_line_badge"), "")
		self.assertIn("test-plugin-banner", storefront_plugins.plugin_slot("cart_banner"))
		self.assertIn("commera: unknown storefront slot cart_line_badge", self.get_error_titles())

	def test_broken_block_still_renders_the_page(self):
		self.declare_hooks({"commera_storefront_blocks": {"cart_banner": [BROKEN, BANNER]}})
		self.set_enabled(1)

		html = get_html_for_route("en/cart")

		self.assertIn("test-plugin-banner", html)
		self.assertNotIn("test-plugin-broken", html)
		self.assertIn(f"Storefront block {BROKEN} failed to render", self.get_error_titles())

	def test_checkout_loads_no_plugin_scripts_or_overlay(self):
		self.declare_full_plugin()
		self.set_enabled(1)

		set_request(method="GET", path="/en/cart/checkout")

		self.assertEqual(storefront_plugins.format_plugin_includes("js"), "")
		self.assertEqual(storefront_plugins.format_plugin_includes("css"), "")
		self.assertEqual(storefront_plugins.plugin_slot("page_overlay"), "")
		self.assertIn("test-plugin-banner", storefront_plugins.plugin_slot("checkout_banner"))
