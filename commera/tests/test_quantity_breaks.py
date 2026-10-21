import frappe
from frappe.utils.data import add_days, today

from commera.api.payments import _make_sales_order, generate_quotation_for_cart, make_sales_invoice
from commera.discounts.codes import get_code_discount
from commera.discounts.preview import get_preview_quotation
from commera.sdk import cart as cart_sdk
from commera.tests import test_server_cart
from commera.tests.test_discount_codes import DiscountCodeTestCase

LIST_RATE = 500.0
BREAK_RATES = {5: 500.0, 10: 450.0, 50: 400.0}


class TestQuantityBreaks(DiscountCodeTestCase):
	def setUp(self):
		super().setUp()
		sale_price_list = frappe.db.get_single_value("Commera Settings", "sale_price_list")
		self.addCleanup(test_server_cart.TestServerCart.set_sale_price_list, self, sale_price_list)
		test_server_cart.TestServerCart.set_sale_price_list(self, self.price_list)

	def create_bulk_item(self, rate_or_discount: str) -> str:
		"""An item at 500 with quantity breaks at 10 (450) and 50 (400), as rates or as percentages off."""
		item_code = self.create_item(LIST_RATE)
		frappe.db.set_value("Bin", {"item_code": item_code, "warehouse": self.warehouse}, "actual_qty", 100)
		for min_qty, max_qty, rate, percentage in ((10, 49, 450, 10), (50, 0, 400, 20)):
			frappe.get_doc(
				{
					"doctype": "Pricing Rule",
					"title": f"ZZ Break {frappe.generate_hash(length=8)}",
					"apply_on": "Item Code",
					"items": [{"item_code": item_code}],
					"selling": 1,
					"currency": self.currency,
					"min_qty": min_qty,
					"max_qty": max_qty,
					"rate_or_discount": rate_or_discount,
					"rate": rate,
					"discount_percentage": percentage,
				}
			).insert(ignore_permissions=True)
		return item_code

	def use_new_shopper(self):
		frappe.set_user(test_server_cart.TestServerCart.create_shopper(self))

	def browser_line(self, item_code: str, qty: int) -> dict:
		return {"item": {"display_name": item_code}, "variant": {"item_code": item_code}, "qty": qty}

	def test_each_quantity_break_prices_the_cart_preview(self):
		for rate_or_discount in ("Rate", "Discount Percentage"):
			item_code = self.create_bulk_item(rate_or_discount)
			for qty, rate in BREAK_RATES.items():
				with self.subTest(rate_or_discount=rate_or_discount, qty=qty):
					quotation = get_preview_quotation([{"item_code": item_code, "qty": qty}])

					self.assertEqual(quotation.items[0].rate, rate)
					self.assertEqual(quotation.net_total, rate * qty)

	def test_the_priced_cart_shows_the_break_price_once_the_quantity_crosses_it(self):
		item_code = self.create_bulk_item("Discount Percentage")
		self.use_new_shopper()

		below = cart_sdk.add_lines([{"item_code": item_code, "qty": 5}])
		crossed = cart_sdk.add_lines([{"item_code": item_code, "qty": 5}])
		bulk = cart_sdk.add_lines([{"item_code": item_code, "qty": 40}])

		self.assertEqual(
			[(cart["lines"][0]["price"], cart["lines"][0]["rate"]) for cart in (below, crossed, bulk)],
			[(500, 500), (500, 450), (500, 400)],
		)
		self.assertEqual([cart["total"] for cart in (below, crossed, bulk)], [2500, 4500, 20000])

	def test_checkout_the_order_and_the_invoice_keep_the_break_price(self):
		for rate_or_discount in ("Rate", "Discount Percentage"):
			item_code = self.create_bulk_item(rate_or_discount)
			with self.subTest(rate_or_discount=rate_or_discount):
				self.use_new_shopper()
				cart_sdk.add_lines([{"item_code": item_code, "qty": 10}])
				quotation = generate_quotation_for_cart({"items": [self.browser_line(item_code, 10)]})
				frappe.set_user("Administrator")
				sales_order, sales_invoice = self.place_and_bill(quotation)

				for doc in (quotation, sales_order, sales_invoice):
					self.assertEqual((doc.items[0].rate, doc.net_total), (450, 4500), doc.doctype)

	def test_codes_come_off_the_break_price(self):
		"""A product code takes its percentage of the break rate, and an order code comes off after it."""
		for rate_or_discount in ("Rate", "Discount Percentage"):
			item_code = self.create_bulk_item(rate_or_discount)
			product = self.create_code(percentage=10, item_codes=(item_code,), combines_with_order=1)
			order = self.create_code(amount=100, combines_with_product=1)
			with self.subTest(rate_or_discount=rate_or_discount):
				self.use_new_shopper()
				cart_sdk.add_lines([{"item_code": item_code, "qty": 10}])
				cart_sdk.add_discount_code(product)
				priced = cart_sdk.add_discount_code(order)
				quotation = generate_quotation_for_cart({"items": [self.browser_line(item_code, 10)]})
				frappe.set_user("Administrator")
				quotation.reload()
				quotation.save(ignore_permissions=True)
				sales_order, sales_invoice = self.place_and_bill(quotation)

				line = priced["lines"][0]
				self.assertEqual((line["rate"], line["code_discount"]), (405, 45))
				self.assertEqual((priced["order_discount"], priced["total"]), (100, 3950))
				for doc in (quotation, sales_order, sales_invoice):
					self.assertEqual(
						(
							doc.items[0].rate,
							doc.items[0].custom_code_discount,
							doc.custom_code_order_discount,
							doc.net_total,
						),
						(405, 45, 100, 3950),
						doc.doctype,
					)
				self.assertEqual(
					frappe.db.get_value("Commera Discount", get_code_discount(product), "discount_given"), 450
				)

	def place_and_bill(self, quotation):
		quotation.submit()
		sales_order = _make_sales_order(quotation.name, ignore_permissions=True)
		sales_order.delivery_date = add_days(today(), 2)
		sales_order.insert(ignore_permissions=True)
		sales_order.submit()
		sales_invoice = make_sales_invoice(sales_order.name)
		sales_invoice.insert(ignore_permissions=True)
		return sales_order, sales_invoice
