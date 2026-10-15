import frappe

from commera.sdk import discounts
from commera.tests.test_discount_codes import SHIRT_RATE, DiscountCodeTestCase


class TestSdkDiscounts(DiscountCodeTestCase):
	def setUp(self):
		super().setUp()
		sale_price_list = frappe.db.get_single_value("Commera Settings", "sale_price_list")
		self.addCleanup(self.set_sale_price_list, sale_price_list)
		self.set_sale_price_list(self.price_list)

	def set_sale_price_list(self, price_list: str):
		frappe.db.set_single_value("Commera Settings", "sale_price_list", price_list)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

	def test_a_code_discount_is_created_with_its_code(self):
		created = discounts.create_discount(
			{"discount_type": "Amount Off Order", "value_type": "Percentage", "value": 10}, code="zz-sdk"
		)

		self.assertEqual(
			(created["title"], created["codes"], created["status"]), ("ZZ-SDK", ["ZZ-SDK"], "Active")
		)
		self.assertEqual(discounts.get_discount(created["name"])["value"], 10)

	def test_a_code_discount_without_a_code_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			discounts.create_discount({"discount_type": "Amount Off Order", "value": 10})

	def test_a_shopper_cannot_create_discounts(self):
		frappe.set_user("Guest")

		with self.assertRaises(frappe.PermissionError):
			discounts.create_discount({"discount_type": "Amount Off Order", "value": 10}, code="zz-guest")

	def test_preview_cart_shows_the_discount_before_checkout(self):
		created = discounts.create_discount(
			{"discount_type": "Amount Off Order", "value_type": "Percentage", "value": 10}, code="zz-preview"
		)

		preview = discounts.preview_cart([{"item_code": self.shirt, "qty": 2}], codes=created["codes"])

		self.assertEqual((preview["subtotal"], preview["total"]), (2 * SHIRT_RATE, 2 * SHIRT_RATE * 0.9))
		self.assertEqual([row["discount"] for row in preview["discounts"]], [created["name"]])

	def test_an_order_reports_its_discounts(self):
		code = self.create_code(percentage=10)
		sales_order = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))

		self.assertEqual([row["amount"] for row in discounts.get_order_discounts(sales_order.name)], [9])
