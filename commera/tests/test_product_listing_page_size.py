# Copyright (c) 2026, company@bwhstudios.com and Contributors
# Tests for the storefront listing controller (commera/utils.py and commera/www/products/list.py):
# page size, and the ?category= a shopper can type. Real-DB, auto-rolled-back.

import frappe
from frappe.tests import IntegrationTestCase

from commera.commera_ecommerce.doctype.commera_settings.navbar import navbar_manager
from commera.shop_themes.render import render_themed_template
from commera.tests import delete_menu_entries, get_test_configurator
from commera.utils import DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS
from commera.www.products import list as products_list

FIXTURE_COUNT = 15
SETTINGS_DOCTYPE = "Commera Settings"
SCRIPT_PAYLOAD = "<script>alert(1)</script>"
PAGE_SIZE_FIELD = "products_per_page"


class ProductListingPageSizeTestCase(IntegrationTestCase):
	"""One item group of published variants, so every listing assertion counts only this test's rows."""

	def setUp(self):
		self.suffix = frappe.generate_hash(length=8).upper()
		self.default_price_list = self.make_price_list("Default")
		self.sale_price_list = self.make_price_list("Sale")

		settings = frappe.get_doc("Commera Settings")
		settings.default_price_list = self.default_price_list
		settings.sale_price_list = self.sale_price_list
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

		self.item_group = self.make_item_group()
		self.configurator = get_test_configurator()
		frappe.local.lang = "en"
		frappe.local.commera_storefront_menu = None
		self.variants = [self.make_variant(index) for index in range(FIXTURE_COUNT)]

		self.configured_page_size = frappe.db.get_single_value(SETTINGS_DOCTYPE, PAGE_SIZE_FIELD)
		# Every assertion below states its own merchant default, so the site's own value cannot leak in.
		self.set_configured_page_size("")

	def tearDown(self):
		self.set_configured_page_size(self.configured_page_size)
		delete_menu_entries({"display_name": ["like", f"%{self.suffix}%"]})
		frappe.local.commera_storefront_menu = None

	def set_configured_page_size(self, page_size):
		"""The controller reads a Single, so a rolled-back value would otherwise linger in Redis."""
		frappe.db.set_single_value(SETTINGS_DOCTYPE, PAGE_SIZE_FIELD, page_size)
		frappe.clear_document_cache(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)

	def make_price_list(self, label):
		price_list = frappe.new_doc("Price List")
		price_list.price_list_name = f"Page Size {label} {self.suffix}"
		price_list.currency = frappe.defaults.get_global_default("currency") or "INR"
		price_list.selling = 1
		price_list.enabled = 1
		price_list.insert()
		return price_list.name

	def make_item_group(self):
		item_group = frappe.new_doc("Item Group")
		item_group.item_group_name = f"Page Size Group {self.suffix}"
		item_group.parent_item_group = "All Item Groups"
		item_group.is_group = 0
		# commera makes the storefront display name mandatory on Item Group.
		item_group.custom_displayname = item_group.item_group_name
		item_group.insert()
		return item_group.name

	def make_item(self, index):
		item = frappe.new_doc("Item")
		item.item_code = f"PAGESIZE-{index}-{self.suffix}"
		item.item_name = item.item_code
		item.item_group = self.item_group
		item.stock_uom = "Nos"
		item.is_stock_item = 1
		item.insert()
		return item.name

	def make_variant(self, index):
		item_code = self.make_item(index)
		item_price = frappe.new_doc("Item Price")
		item_price.item_code = item_code
		item_price.price_list = self.default_price_list
		item_price.price_list_rate = 100 + index
		item_price.insert()

		variant = frappe.new_doc("Style Attribute Variant")
		variant.configurator = self.configurator
		variant.item_style = item_code
		variant.item_group = self.item_group
		variant.attribute_value = f"Val {index} {self.suffix}"
		variant.display_name = f"Page Size Product {index} {self.suffix}"
		variant.route = f"page-size-{index}-{self.suffix.lower()}"
		# images + sizes are required or validate() force-unpublishes the variant
		variant.append("images", {"image": "/assets/page-size-test.jpg"})
		variant.append("sizes", {"size": "M", "item_code": item_code})
		variant.is_published = 1
		variant.insert(ignore_permissions=True)
		return variant.name

	def get_listing(self, **query_params):
		"""Render the listing controller for this test's item group under the given query string."""
		context = frappe._dict()
		# frappe.local, never frappe.form_dict — see the note in test_admin_theme.render().
		frappe.local.form_dict = frappe._dict(subcategory=self.item_group, **query_params)
		products_list.get_context(context)
		return context

	def test_default_page_size_when_param_absent(self):
		self.assertEqual(self.get_listing().page_length, DEFAULT_PAGE_SIZE)

	def test_every_offered_option_is_honoured(self):
		for option in PAGE_SIZE_OPTIONS:
			with self.subTest(page_size=option):
				self.assertEqual(self.get_listing(page_size=str(option)).page_length, option)

	def test_unusable_values_fall_back_to_the_default(self):
		for page_size in ("abc", "-5", "0", "9999", "", "30"):
			with self.subTest(page_size=page_size):
				self.assertEqual(self.get_listing(page_size=page_size).page_length, DEFAULT_PAGE_SIZE)

	def test_page_size_caps_the_rows_rendered(self):
		context = self.get_listing(page_size="12")
		self.assertEqual(context.total_count, FIXTURE_COUNT)
		self.assertEqual(len(context.products), 12)

	def test_second_page_holds_the_remainder_and_repeats_nothing(self):
		first_page = self.get_listing(page_size="12")
		second_page = self.get_listing(page_size="12", page="2")

		self.assertEqual(second_page.current_page, 2)
		self.assertEqual(len(second_page.products), FIXTURE_COUNT - 12)
		first_names = {product["name"] for product in first_page.products}
		second_names = {product["name"] for product in second_page.products}
		self.assertTrue(first_names.isdisjoint(second_names))

	def test_a_larger_page_size_swallows_the_second_page(self):
		self.assertEqual(len(self.get_listing(page_size="48").products), FIXTURE_COUNT)

	def test_options_reach_the_template(self):
		self.assertEqual(self.get_listing().page_size_options, PAGE_SIZE_OPTIONS)

	def test_merchant_setting_drives_the_default(self):
		for option in PAGE_SIZE_OPTIONS:
			with self.subTest(products_per_page=option):
				self.set_configured_page_size(str(option))
				self.assertEqual(self.get_listing().page_length, option)

	def test_shopper_choice_overrides_the_merchant_setting(self):
		self.set_configured_page_size("48")
		self.assertEqual(self.get_listing(page_size="12").page_length, 12)

	def test_unset_setting_falls_back_to_the_default(self):
		for products_per_page in (None, ""):
			with self.subTest(products_per_page=products_per_page):
				self.set_configured_page_size(products_per_page)
				self.assertEqual(self.get_listing().page_length, DEFAULT_PAGE_SIZE)

	def test_unusable_setting_falls_back_to_the_default(self):
		for products_per_page in ("abc", "0", "-5", "30", "9999"):
			with self.subTest(products_per_page=products_per_page):
				self.set_configured_page_size(products_per_page)
				self.assertEqual(self.get_listing().page_length, DEFAULT_PAGE_SIZE)

	def test_unusable_param_falls_back_to_the_setting_not_the_default(self):
		self.set_configured_page_size("12")
		for page_size in ("abc", "0", "-5", "30", ""):
			with self.subTest(page_size=page_size):
				self.assertEqual(self.get_listing(page_size=page_size).page_length, 12)

	def get_listing_html(self, **query_params):
		context = self.get_listing(**query_params)
		return render_themed_template("theme://pages/products/list.html", context, theme_name="Summer Theme")

	def test_unknown_category_is_dropped_and_the_other_filters_still_apply(self):
		context = self.get_listing(category=f"stale-tab-{self.suffix.lower()}")

		self.assertEqual(context.category, "")
		self.assertEqual(context.selected_filters["category"], "")
		self.assertEqual(context.total_count, FIXTURE_COUNT)

	def test_script_in_category_is_never_echoed(self):
		context = self.get_listing(category=SCRIPT_PAYLOAD)
		self.assertNotIn(
			"alert(1)", frappe.as_json([context.category, context.seo, context.json_ld, context.filters])
		)
		self.assertEqual(context.total_count, FIXTURE_COUNT)

		self.assertNotIn("alert(1)", self.get_listing_html(category=SCRIPT_PAYLOAD))

	def test_script_in_a_filter_chip_is_escaped(self):
		html = self.get_listing_html(colors=SCRIPT_PAYLOAD)

		self.assertNotIn(SCRIPT_PAYLOAD, html)
		self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)

	def test_known_category_heads_the_page_with_its_label(self):
		label = f"Listing Tab {self.suffix}"
		route_slug = f"listing-tab-{self.suffix.lower()}"
		tab = navbar_manager.create_node("", label)
		frappe.db.set_value(
			"Ecommerce Category", tab.name, {"route_slug": route_slug, "meta_title": f"Meta {label}"}
		)
		frappe.local.commera_storefront_menu = None

		for category in (route_slug, tab.name, label):
			with self.subTest(category=category):
				context = self.get_listing(category=category)

				self.assertEqual(context.category, label)
				self.assertEqual(context.total_count, FIXTURE_COUNT)
				self.assertEqual(context.seo["title"], f"Meta {label}")
				self.assertIn(label, context.filters)
				self.assertIn(f"<h1>{label}</h1>", self.get_listing_html(category=category))
