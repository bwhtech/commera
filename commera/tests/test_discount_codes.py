import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.data import add_days, today

from commera.api.payments import _make_sales_order, make_sales_invoice
from commera.core import new_cart_quotation
from commera.discount_codes import (
	MAX_DISCOUNT_CODES,
	DiscountCodeError,
	validate_new_discount_code,
)

SHIRT_RATE = 90.0
CAP_RATE = 40.0


class DiscountCodeTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		settings = frappe.get_cached_doc("Commera Settings")
		cls.warehouse = settings.ecommerce_warehouse
		company = settings.get("company") or frappe.defaults.get_global_default("company")
		cls.currency = frappe.get_cached_value("Company", company, "default_currency")
		# In the company currency, so rates are not converted and the expected numbers stay readable.
		cls.price_list = "ZZ Discount Code Prices"
		if not frappe.db.exists("Price List", cls.price_list):
			frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": cls.price_list,
					"currency": cls.currency,
					"selling": 1,
				}
			).insert(ignore_permissions=True)

	def setUp(self):
		self.addCleanup(frappe.set_user, "Administrator")
		self.shirt = self.create_item(SHIRT_RATE)
		self.cap = self.create_item(CAP_RATE)

	def create_item(self, rate: float) -> str:
		item_code = f"ZZ-CODE-{frappe.generate_hash(length=8)}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": frappe.get_all("Item Group", {"is_group": 0}, pluck="name", limit=1)[0],
				"stock_uom": "Nos",
				"is_stock_item": 1,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": self.price_list,
				"price_list_rate": rate,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{"doctype": "Bin", "item_code": item_code, "warehouse": self.warehouse, "actual_qty": 10}
		).insert(ignore_permissions=True)
		return item_code

	def create_code(
		self,
		percentage: float = 0,
		amount: float = 0,
		item_codes: tuple[str, ...] = (),
		**discount_fields,
	) -> str:
		"""A Product code on `item_codes` when given, else an Order code."""
		return (
			frappe.get_doc(
				{
					"doctype": "Commera Discount",
					"code": f"zz{frappe.generate_hash(length=8)}",
					"discount_class": "Product" if item_codes else "Order",
					"value_type": "Percentage" if percentage else "Fixed Amount",
					"value": percentage or amount,
					"currency": self.currency,
					"targets": [{"target_type": "Item", "target": item_code} for item_code in item_codes],
					**discount_fields,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def create_automatic_rule(self, item_code: str, percentage: float):
		frappe.get_doc(
			{
				"doctype": "Pricing Rule",
				"title": f"ZZ Auto {frappe.generate_hash(length=8)}",
				"apply_on": "Item Code",
				"items": [{"item_code": item_code}],
				"rate_or_discount": "Discount Percentage",
				"discount_percentage": percentage,
				"selling": 1,
				"currency": self.currency,
			}
		).insert(ignore_permissions=True)

	def create_quotation(self, lines: dict[str, int], codes: tuple[str, ...] = ()):
		customer = frappe.get_doc(
			{"doctype": "Customer", "customer_name": f"ZZ Code Shopper {frappe.generate_hash(length=6)}"}
		).insert(ignore_permissions=True)
		quotation = new_cart_quotation(customer, "zz-code-shopper@example.com")
		quotation.selling_price_list = self.price_list
		for item_code, qty in lines.items():
			quotation.append("items", {"item_code": item_code, "qty": qty, "warehouse": self.warehouse})
		quotation.custom_discount_codes = "\n".join(codes)
		quotation.insert(ignore_permissions=True)
		return quotation

	def get_line(self, doc, item_code: str):
		return next(row for row in doc.items if row.item_code == item_code)


class TestDiscountCodes(DiscountCodeTestCase):
	def test_a_product_code_discounts_only_its_items(self):
		code = self.create_code(percentage=10, item_codes=(self.shirt,))

		quotation = self.create_quotation({self.shirt: 2, self.cap: 1}, (code,))

		shirt = self.get_line(quotation, self.shirt)
		self.assertEqual(shirt.rate, 81)
		self.assertEqual(shirt.custom_code_discount, 9)
		self.assertEqual(shirt.custom_discount_code, code)
		self.assertEqual(self.get_line(quotation, self.cap).rate, CAP_RATE)
		self.assertEqual(quotation.net_total, 2 * 81 + CAP_RATE)

	def test_the_best_product_code_wins_on_a_line(self):
		small = self.create_code(percentage=10, item_codes=(self.shirt,), combines_with_product=1)
		large = self.create_code(amount=20, item_codes=(self.shirt,), combines_with_product=1)

		quotation = self.create_quotation({self.shirt: 1}, (small, large))

		shirt = self.get_line(quotation, self.shirt)
		self.assertEqual(shirt.rate, 70)
		self.assertEqual(shirt.custom_discount_code, large)

	def test_an_order_code_comes_off_the_subtotal_after_product_codes(self):
		product = self.create_code(amount=10, item_codes=(self.shirt,), combines_with_order=1)
		order = self.create_code(percentage=10, combines_with_product=1)

		quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, (product, order))

		self.assertEqual(quotation.total, 80 + CAP_RATE)
		self.assertEqual(quotation.custom_code_order_discount, 12)
		self.assertEqual(quotation.net_total, 108)

	def test_saving_again_does_not_apply_a_code_twice(self):
		code = self.create_code(percentage=10, item_codes=(self.shirt,))
		quotation = self.create_quotation({self.shirt: 1}, (code,))

		quotation.save(ignore_permissions=True)
		quotation.reload()
		quotation.save(ignore_permissions=True)

		self.assertEqual(self.get_line(quotation, self.shirt).rate, 81)

	def test_a_code_stacks_on_an_automatic_pricing_rule_across_saves(self):
		"""ERPNext rebuilds an automatic rule's discount on every save; the code must survive that."""
		self.create_automatic_rule(self.shirt, percentage=10)
		code = self.create_code(amount=5, item_codes=(self.shirt,))

		quotation = self.create_quotation({self.shirt: 1}, (code,))
		quotation.reload()
		quotation.save(ignore_permissions=True)

		shirt = self.get_line(quotation, self.shirt)
		self.assertEqual(shirt.rate, 90 - 9 - 5)
		self.assertEqual(shirt.discount_amount, 14)

	def test_codes_combine_only_when_both_allow_it(self):
		product = self.create_code(percentage=10, item_codes=(self.shirt,), combines_with_order=1)
		strict_order = self.create_code(percentage=5)
		open_order = self.create_code(percentage=5, combines_with_product=1)
		applied = [product]

		with self.assertRaises(DiscountCodeError):
			validate_new_discount_code(strict_order, applied)
		self.assertEqual(validate_new_discount_code(open_order, applied), open_order)

	def test_a_cart_holds_a_limited_number_of_codes(self):
		codes = [
			self.create_code(percentage=1, combines_with_order=1) for _index in range(MAX_DISCOUNT_CODES)
		]

		with self.assertRaises(DiscountCodeError):
			validate_new_discount_code(self.create_code(percentage=1, combines_with_order=1), codes)

	def test_an_expired_code_is_refused(self):
		code = self.create_code(percentage=10, valid_upto=add_days(today(), -1))

		with self.assertRaises(DiscountCodeError):
			validate_new_discount_code(code, [])

	def test_codes_are_matched_without_case(self):
		code = self.create_code(percentage=10)

		self.assertEqual(validate_new_discount_code(f" {code.lower()} ", []), code)


class TestDiscountCodesOnOrders(DiscountCodeTestCase):
	def test_the_sales_order_keeps_code_discounts_and_counts_uses(self):
		product = self.create_code(percentage=10, item_codes=(self.shirt,), combines_with_order=1)
		order = self.create_code(amount=5, combines_with_product=1)
		quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, (product, order))
		quotation.submit()

		sales_order = _make_sales_order(quotation.name, ignore_permissions=True)
		sales_order.delivery_date = add_days(today(), 2)
		sales_order.insert(ignore_permissions=True)
		sales_order.submit()

		self.assertEqual(self.get_line(sales_order, self.shirt).rate, 81)
		self.assertEqual(sales_order.custom_code_order_discount, 5)
		self.assertEqual(sales_order.net_total, quotation.net_total)
		self.assertEqual(frappe.db.get_value("Commera Discount", product, "times_used"), 1)

		sales_order.cancel()
		self.assertEqual(frappe.db.get_value("Commera Discount", product, "times_used"), 0)

	def test_the_invoice_keeps_code_discounts_over_an_automatic_rule(self):
		"""ERPNext prices the invoice again; with an automatic rule on the line that drops an unhooked code."""
		self.create_automatic_rule(self.shirt, percentage=10)
		code = self.create_code(amount=5, item_codes=(self.shirt,))
		quotation = self.create_quotation({self.shirt: 1}, (code,))
		quotation.submit()
		sales_order = _make_sales_order(quotation.name, ignore_permissions=True)
		sales_order.delivery_date = add_days(today(), 2)
		sales_order.insert(ignore_permissions=True)
		sales_order.submit()

		sales_invoice = make_sales_invoice(sales_order.name)
		sales_invoice.insert(ignore_permissions=True)

		self.assertEqual(self.get_line(sales_invoice, self.shirt).rate, 90 - 9 - 5)
		self.assertEqual(sales_invoice.net_total, sales_order.net_total)

	def test_an_order_is_refused_when_its_code_is_used_up(self):
		code = self.create_code(percentage=10, usage_limit=1, times_used=1)
		quotation = self.create_quotation({self.shirt: 1}, (code,))
		quotation.submit()
		sales_order = _make_sales_order(quotation.name, ignore_permissions=True)
		sales_order.delivery_date = add_days(today(), 2)
		sales_order.insert(ignore_permissions=True)

		with self.assertRaises(DiscountCodeError):
			sales_order.submit()
