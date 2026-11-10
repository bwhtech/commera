from unittest.mock import patch

import frappe

from commera.localization import register
from commera.sdk import cart as cart_sdk
from commera.sdk import checkout, lines, orders
from commera.tests import test_cart_checkout, test_checkout_hooks
from commera.tests.test_admin_orders import ensure_fiscal_year, make_test_sales_order
from commera.tests.test_content_translation import use_storefront_language
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_product_details import ProductDetailPriceTestCase

PRODUCT = "Style Attribute Variant"
ARABIC_TITLE = "قميص كتان"


class TestLineTranslation(ProductDetailPriceTestCase):
	create_shopper = test_cart_checkout.TestCartCheckout.create_shopper
	cart_line = test_cart_checkout.TestCartCheckout.cart_line
	address_payload = test_cart_checkout.TestCartCheckout.address_payload
	open_cart = test_checkout_hooks.TestCheckoutHooks.open_cart

	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.set_user, "Administrator")
		ensure_fiscal_year()
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.add_frappe_translation("M", "وسط")
		self.add_frappe_translation("L", "كبير")
		self.product = frappe.get_doc(PRODUCT, {"route": self.make_priced_variant("LINES", default_rate=40)})
		register(PRODUCT, self.product.name, "display_name", "ar", ARABIC_TITLE)
		self.item = self.product.sizes[0].item_code
		self.large_item = self.add_size("L")
		self.stock(self.item, self.large_item)
		self.shopper = self.create_shopper()

	def add_size(self, size):
		item_code = self.make_item(f"LINES-{size}")
		self.make_item_price(item_code, self.default_price_list, 40)
		self.product.append("sizes", {"size": size, "item_code": item_code})
		self.product.save(ignore_permissions=True)
		return item_code

	def stock(self, *item_codes):
		for item_code in item_codes:
			frappe.get_doc(
				{"doctype": "Bin", "item_code": item_code, "warehouse": self.warehouse, "actual_qty": 10}
			).insert(ignore_permissions=True)

	def add_frappe_translation(self, source, translated):
		translation = frappe.get_doc(
			{"doctype": "Translation", "language": "ar", "source_text": source, "translated_text": translated}
		).insert()
		self.addCleanup(
			frappe.delete_doc, "Translation", translation.name, force=True, ignore_permissions=True
		)

	def test_only_a_non_default_arabic_request_reads_legacy_item_titles(self):
		has_column = frappe.db.has_column

		def no_item_reads(doctype, column):
			self.assertNotEqual(doctype, "Item", "the default language read legacy Item titles")
			return has_column(doctype, column)

		use_storefront_language(self, "en")
		with patch.object(frappe.db, "has_column", no_item_reads):
			self.assertEqual(lines.read_legacy_titles(["ANY-STYLE"]), {})

	def test_cart_lines_show_the_translated_product_title_and_size(self):
		frappe.set_user(self.shopper)
		use_storefront_language(self, "ar")
		line = cart_sdk.add_lines([{"item_code": self.item, "qty": 1}])["lines"][0]

		self.assertEqual(line["title"], f"{ARABIC_TITLE} - وسط")
		self.assertEqual((line["product"]["title"], line["product"]["variant_title"]), (ARABIC_TITLE, "وسط"))
		self.assertEqual(line["item_code"], self.item)

		use_storefront_language(self, "en")
		line = cart_sdk.get_priced_cart()["lines"][0]
		self.assertEqual(line["title"], frappe.db.get_value("Item", self.item, "item_name"))
		self.assertEqual(
			(line["product"]["title"], line["product"]["variant_title"]), (self.product.display_name, "M")
		)

	def test_changing_a_cart_line_variant_keeps_the_translated_title(self):
		frappe.set_user(self.shopper)
		use_storefront_language(self, "ar")
		priced = cart_sdk.add_lines([{"item_code": self.item, "qty": 1}])

		priced = cart_sdk.set_lines([{"item_code": self.large_item, "qty": 1}], priced["revision"])

		line = priced["lines"][0]
		self.assertEqual((line["item_code"], line["title"]), (self.large_item, f"{ARABIC_TITLE} - كبير"))
		self.assertEqual((line["product"]["title"], line["product"]["variant_title"]), (ARABIC_TITLE, "كبير"))

	def test_the_cart_and_checkout_lines_show_the_translated_title(self):
		self.open_cart(qty=1)
		use_storefront_language(self, "ar")

		self.assertEqual(cart_sdk.get_cart()["items"][0]["title"], f"{ARABIC_TITLE} - وسط")
		self.assertEqual(checkout.get()["items"][0]["title"], f"{ARABIC_TITLE} - وسط")

	def test_order_lines_show_the_translated_title_in_one_translation_read(self):
		sold, unlisted = make_test_sales_order(), make_test_sales_order()
		route = f"details-test-order-{self.suffix.lower()}"
		product = self.make_variant(sold.items[0].item_code, route)
		register(PRODUCT, product.name, "display_name", "ar", "حذاء")
		use_storefront_language(self, "ar")

		with patch.object(lines, "translate_products", wraps=lines.translate_products) as translate_products:
			found = orders.get_orders([sold.name, unlisted.name])

		self.assertEqual(translate_products.call_count, 1)
		self.assertEqual(found[sold.name]["items"][0]["title"], "حذاء - وسط")
		self.assertEqual(found[unlisted.name]["items"][0]["title"], unlisted.items[0].item_name)
		self.assertEqual(found[sold.name]["items"][0]["item_code"], sold.items[0].item_code)
