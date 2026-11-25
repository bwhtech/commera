# Copyright (c) 2026, ivend and Contributors
# Tests for the product detail page price fallback (commera/www/products/details.py
# and commera/product_detail.py). Real-DB, auto-rolled-back.

import frappe
from frappe.tests import IntegrationTestCase

from commera.product_detail import DEFAULT_PRODUCT_IMAGE, get_product_detail
from commera.tests import get_test_configurator
from commera.utils import get_discount_percent
from commera.www.products import details


class ProductDetailPriceTestCase(IntegrationTestCase):
	"""One published variant per pricing scenario, each on its own item so the price cache cannot bleed."""

	def setUp(self):
		self.suffix = frappe.generate_hash(length=8).upper()
		self.default_price_list = self.make_price_list("Default")
		self.sale_price_list = self.make_price_list("Sale")
		self.warehouse = frappe.db.get_value("Warehouse", {"is_group": 0}, "name")

		settings = frappe.get_doc("Commera Settings")
		settings.default_price_list = self.default_price_list
		settings.sale_price_list = self.sale_price_list
		settings.ecommerce_warehouse = self.warehouse
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

		self.item_group = self.make_item_group()
		self.configurator = get_test_configurator()
		frappe.local.lang = "en"

	def make_price_list(self, label):
		price_list = frappe.new_doc("Price List")
		price_list.price_list_name = f"Details {label} {self.suffix}"
		price_list.currency = frappe.defaults.get_global_default("currency") or "INR"
		price_list.selling = 1
		price_list.enabled = 1
		price_list.insert()
		return price_list.name

	def make_item_group(self):
		item_group = frappe.new_doc("Item Group")
		item_group.item_group_name = f"Details Group {self.suffix}"
		item_group.parent_item_group = "All Item Groups"
		item_group.is_group = 0
		# commera makes the storefront display name mandatory on Item Group.
		item_group.custom_displayname = item_group.item_group_name
		item_group.insert()
		return item_group.name

	def make_item(self, label):
		item = frappe.new_doc("Item")
		item.item_code = f"DETAILS-{label}-{self.suffix}"
		item.item_name = item.item_code
		item.item_group = self.item_group
		item.stock_uom = "Nos"
		item.is_stock_item = 1
		item.insert()
		return item.name

	def make_item_price(self, item_code, price_list, rate):
		item_price = frappe.new_doc("Item Price")
		item_price.item_code = item_code
		item_price.price_list = price_list
		item_price.price_list_rate = rate
		item_price.insert()
		return item_price.name

	def make_variant(self, item_code, route, image="/assets/details-test.jpg"):
		variant = frappe.new_doc("Style Attribute Variant")
		variant.configurator = self.configurator
		variant.item_style = item_code
		variant.item_group = self.item_group
		variant.attribute_value = f"Val {frappe.generate_hash(length=6)}"
		variant.display_name = f"Display {route}"
		variant.route = route
		if image:
			variant.append("images", {"image": image})
		variant.append("sizes", {"size": "M", "item_code": item_code})
		variant.is_published = 1
		variant.insert(ignore_permissions=True)
		return variant

	def make_priced_variant(self, label, default_rate, sale_rate=None):
		item_code = self.make_item(label)
		if default_rate is not None:
			self.make_item_price(item_code, self.default_price_list, default_rate)
		if sale_rate is not None:
			self.make_item_price(item_code, self.sale_price_list, sale_rate)
		route = f"details-test-{label.lower()}-{self.suffix.lower()}"
		self.make_variant(item_code, route)
		return route

	def render(self, route):
		# frappe.local, never frappe.form_dict — see the note in test_admin_theme.render().
		frappe.local.form_dict = frappe._dict(route=route)
		context = frappe._dict()
		details.get_context(context)
		return context


class TestProductDetailImages(ProductDetailPriceTestCase):
	def test_a_product_without_a_photo_is_published_with_no_images(self):
		item_code = self.make_item("NOPHOTO")
		route = f"details-test-nophoto-{self.suffix.lower()}"
		self.make_variant(item_code, route, image=None)

		self.assertEqual(get_product_detail(route)["images"], [])
		context = self.render(route)
		self.assertEqual(context.images, [DEFAULT_PRODUCT_IMAGE])
		product = next(entry for entry in context.json_ld if entry.get("@type") == "Product")
		self.assertNotIn(DEFAULT_PRODUCT_IMAGE, str(product.get("image")))


class TestProductDetailPrice(ProductDetailPriceTestCase):
	def test_default_price_shows_when_no_sale_row_exists(self):
		# Reported as #58: a product absent from the sale price list rendered 0.
		route = self.make_priced_variant("NOSALE", default_rate=25)
		context = self.render(route)

		self.assertEqual(context.selected_price, 25)
		self.assertEqual(context.default_price, 25)
		self.assertEqual(context.discount_percent, 0)

	def test_sale_price_still_wins_when_a_sale_row_exists(self):
		route = self.make_priced_variant("ONSALE", default_rate=100, sale_rate=80)
		context = self.render(route)

		self.assertEqual(context.selected_price, 80)
		self.assertEqual(context.default_price, 100)
		self.assertEqual(context.discount_percent, 20)

	def test_schema_price_matches_the_visible_price(self):
		# add_seo used to be the only caller applying the fallback, so the two disagreed.
		route = self.make_priced_variant("SCHEMA", default_rate=25)
		context = self.render(route)

		self.assertEqual(context.seo["price"], f"{context.selected_price:.2f}")
		offers = next(entry for entry in context.json_ld if entry.get("@type") == "Product")["offers"]
		self.assertEqual(offers["price"], f"{context.selected_price:.2f}")

	def test_free_sale_row_is_not_mistaken_for_a_missing_one(self):
		route = self.make_priced_variant("FREE", default_rate=40, sale_rate=0)
		detail = get_product_detail(route)

		self.assertEqual(detail["sale_price"], 0)
		self.assertEqual(detail["selected_price"], 0)
		self.assertEqual(detail["discount_percent"], 100)

	def test_missing_sale_row_reads_as_none_not_zero(self):
		route = self.make_priced_variant("NOROW", default_rate=40)
		detail = get_product_detail(route)

		self.assertIsNone(detail["sale_price"])
		self.assertEqual(detail["selected_price"], 40)


class TestGetDiscountPercent(IntegrationTestCase):
	def test_missing_sale_price_is_no_discount(self):
		self.assertEqual(get_discount_percent(25, None), 0)

	def test_free_sale_price_is_a_full_discount(self):
		self.assertEqual(get_discount_percent(40, 0), 100)

	def test_sale_price_above_default_is_no_discount(self):
		self.assertEqual(get_discount_percent(40, 50), 0)

	def test_missing_default_price_is_no_discount(self):
		self.assertEqual(get_discount_percent(0, 10), 0)
		self.assertEqual(get_discount_percent(None, 10), 0)
