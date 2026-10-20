from unittest.mock import patch

import frappe
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from frappe.tests import IntegrationTestCase
from frappe.utils.data import add_days, money_in_words, today

from commera.api.payments import (
	CheckoutPriceChangedError,
	_make_sales_order,
	drop_refused_codes,
	make_sales_invoice,
)
from commera.api.shipping import apply_delivery_option, get_checkout_summary
from commera.commera_ecommerce.doctype.commera_discount.commera_discount import DiscountCodeError
from commera.core import new_cart_quotation
from commera.discounts.codes import add_code, generate_codes, get_code_discount
from commera.discounts.pricing import refresh_code_discounts
from commera.discounts.selection import MAX_DISCOUNT_CODES, validate_new_discount_code
from commera.discounts.shipping import apply_shipping_discounts

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
		self.customer = self.create_customer()

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
		self.set_price(item_code, self.price_list, rate)
		frappe.get_doc(
			{"doctype": "Bin", "item_code": item_code, "warehouse": self.warehouse, "actual_qty": 10}
		).insert(ignore_permissions=True)
		return item_code

	def set_price(self, item_code: str, price_list: str, rate: float):
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": price_list,
				"price_list_rate": rate,
			}
		).insert(ignore_permissions=True)

	def create_customer(self, customer_group: str | None = None):
		return frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"ZZ Code Shopper {frappe.generate_hash(length=6)}",
				**({"customer_group": customer_group} if customer_group else {}),
			}
		).insert(ignore_permissions=True)

	def create_discount(
		self, percentage: float = 0, amount: float = 0, item_codes: tuple[str, ...] = (), **fields
	) -> str:
		"""Amount off products on `item_codes` when given, else amount off the order."""
		discount = frappe.get_doc(
			{
				"doctype": "Commera Discount",
				"title": f"ZZ {frappe.generate_hash(length=6)}",
				"discount_type": "Amount Off Products" if item_codes else "Amount Off Order",
				"applies_to": "Specific Products" if item_codes else "All Products",
				"value_type": "Percentage" if percentage else "Fixed Amount",
				"value": percentage or amount,
				"currency": self.currency,
				"targets": [
					{"role": "Applies To", "target_type": "Item", "target": code} for code in item_codes
				],
				**fields,
			}
		).insert(ignore_permissions=True)
		return discount.name

	def create_code(self, percentage: float = 0, amount: float = 0, item_codes=(), **fields) -> str:
		discount = self.create_discount(percentage, amount, item_codes, **fields)
		return add_code(discount, f"zz{frappe.generate_hash(length=8)}")

	def create_quotation(self, lines: dict[str, int], codes=(), customer=None, order_type="Shopping Cart"):
		customer = customer or self.customer
		quotation = new_cart_quotation(customer, f"{customer.name.lower().replace(' ', '-')}@example.com")
		quotation.order_type = order_type
		quotation.selling_price_list = self.price_list
		for item_code, qty in lines.items():
			quotation.append("items", {"item_code": item_code, "qty": qty, "warehouse": self.warehouse})
		quotation.custom_discount_codes = "\n".join(codes)
		quotation.insert(ignore_permissions=True)
		return quotation

	def place_order(self, quotation):
		quotation.submit()
		sales_order = _make_sales_order(quotation.name, ignore_permissions=True)
		sales_order.delivery_date = add_days(today(), 2)
		sales_order.insert(ignore_permissions=True)
		return sales_order

	def get_line(self, doc, item_code: str):
		return next(row for row in doc.items if row.item_code == item_code)

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


class TestDiscountCodes(DiscountCodeTestCase):
	def test_a_product_code_discounts_only_its_items(self):
		code = self.create_code(percentage=10, item_codes=(self.shirt,))

		quotation = self.create_quotation({self.shirt: 2, self.cap: 1}, (code,))

		shirt = self.get_line(quotation, self.shirt)
		self.assertEqual((shirt.rate, shirt.custom_code_discount), (81, 9))
		self.assertEqual(shirt.custom_discount_code, get_code_discount(code))
		self.assertEqual(self.get_line(quotation, self.cap).rate, CAP_RATE)
		self.assertEqual(quotation.net_total, 2 * 81 + CAP_RATE)

	def test_the_best_product_code_wins_on_a_line(self):
		small = self.create_code(percentage=10, item_codes=(self.shirt,), combines_with_product=1)
		large = self.create_code(amount=20, item_codes=(self.shirt,), combines_with_product=1)

		quotation = self.create_quotation({self.shirt: 1}, (small, large))

		shirt = self.get_line(quotation, self.shirt)
		self.assertEqual(shirt.rate, 70)
		self.assertEqual(shirt.custom_discount_code, get_code_discount(large))

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
		self.assertEqual((shirt.rate, shirt.discount_amount), (90 - 9 - 5, 14))

	def test_a_percentage_is_capped_for_the_whole_order(self):
		code = self.create_code(percentage=10, maximum_discount=5)

		quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, (code,))

		self.assertEqual(quotation.custom_code_order_discount, 5)

	def test_the_best_spend_tier_reached_applies(self):
		code = self.create_code(
			percentage=1,
			tiered=1,
			tiers=[{"minimum_subtotal": 100, "value": 10}, {"minimum_subtotal": 200, "value": 20}],
		)

		reached = self.create_quotation({self.shirt: 1, self.cap: 1}, (code,))
		missed = self.create_quotation({self.cap: 2}, (code,))

		self.assertEqual(reached.custom_code_order_discount, 13)
		self.assertFalse(missed.custom_code_order_discount)

	def test_spend_tiers_entered_from_highest_to_lowest_pick_the_highest_reached(self):
		code = self.create_code(
			percentage=1,
			tiered=1,
			tiers=[{"minimum_subtotal": 200, "value": 20}, {"minimum_subtotal": 100, "value": 10}],
		)
		frappe.clear_document_cache("Commera Discount", get_code_discount(code))

		highest = self.create_quotation({self.shirt: 2, self.cap: 1}, (code,))
		lowest = self.create_quotation({self.shirt: 1, self.cap: 1}, (code,))

		self.assertEqual(highest.custom_code_order_discount, 44)
		self.assertEqual(lowest.custom_code_order_discount, 13)

	def test_items_already_on_sale_get_no_extra_discount(self):
		settings = frappe.get_cached_doc("Commera Settings")
		self.set_price(self.shirt, settings.get_default_price_list(), 200)
		self.set_price(self.shirt, settings.get_sale_price_list(), 100)
		code = self.create_code(percentage=10, item_codes=(self.shirt, self.cap), exclude_sale_items=1)

		quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, (code,))

		self.assertEqual(self.get_line(quotation, self.shirt).rate, SHIRT_RATE)
		self.assertEqual(self.get_line(quotation, self.cap).rate, 36)

	def test_buy_x_get_y_discounts_the_cheapest_rewarded_units(self):
		code = self.create_code(
			discount_type="Buy X Get Y",
			buy_value=2,
			get_quantity=1,
			uses_per_order=1,
			targets=[
				{"role": "Buys", "target_type": "Item", "target": self.shirt},
				{"role": "Gets", "target_type": "Item", "target": self.cap},
			],
		)

		quotation = self.create_quotation({self.shirt: 2, self.cap: 3}, (code,))

		self.assertAlmostEqual(self.get_line(quotation, self.cap).amount, 2 * CAP_RATE, places=1)
		self.assertEqual(self.get_line(quotation, self.shirt).rate, SHIRT_RATE)

	def test_buy_x_get_y_needs_the_bought_units(self):
		code = self.create_code(
			discount_type="Buy X Get Y",
			buy_value=2,
			get_quantity=1,
			targets=[
				{"role": "Buys", "target_type": "Item", "target": self.shirt},
				{"role": "Gets", "target_type": "Item", "target": self.cap},
			],
		)

		quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, (code,))

		self.assertEqual(self.get_line(quotation, self.cap).rate, CAP_RATE)

	def test_a_budget_caps_the_discount(self):
		code = self.create_code(percentage=50, item_codes=(self.shirt,), budget=20)

		quotation = self.create_quotation({self.shirt: 1}, (code,))

		self.assertEqual(self.get_line(quotation, self.shirt).rate, SHIRT_RATE - 20)


class TestDiscountSelection(DiscountCodeTestCase):
	def test_codes_combine_only_when_both_allow_it(self):
		product = self.create_code(percentage=10, item_codes=(self.shirt,), combines_with_order=1)
		strict_order = self.create_code(percentage=5)
		open_order = self.create_code(percentage=5, combines_with_product=1)

		with self.assertRaises(DiscountCodeError):
			validate_new_discount_code(strict_order, [product])
		self.assertEqual(validate_new_discount_code(open_order, [product]), open_order)

	def test_one_discount_applies_once_whatever_codes_it_has(self):
		code = self.create_code(amount=10)
		second_code = add_code(get_code_discount(code), f"zz{frappe.generate_hash(length=8)}")

		with self.assertRaisesRegex(DiscountCodeError, "same discount"):
			validate_new_discount_code(second_code, [code])
		quotation = self.create_quotation({self.shirt: 1}, (code, second_code))

		self.assertEqual(quotation.custom_code_order_discount, 10)
		self.assertEqual(quotation.net_total, SHIRT_RATE - 10)

	def test_a_cart_holds_a_limited_number_of_codes(self):
		codes = [
			self.create_code(percentage=1, combines_with_order=1) for _index in range(MAX_DISCOUNT_CODES)
		]

		with self.assertRaises(DiscountCodeError):
			validate_new_discount_code(self.create_code(percentage=1, combines_with_order=1), codes)

	def test_an_expired_code_is_refused(self):
		code = self.create_code(percentage=10, starts_on=add_days(today(), -9), ends_on=add_days(today(), -1))

		with self.assertRaises(DiscountCodeError):
			validate_new_discount_code(code, [])

	def test_codes_are_matched_without_case(self):
		code = self.create_code(percentage=10)

		self.assertEqual(validate_new_discount_code(f" {code.lower()} ", []), code)

	def test_an_automatic_discount_applies_to_store_carts_only(self):
		self.create_discount(percentage=10, method="Automatic")

		cart = self.create_quotation({self.shirt: 1})
		desk_quotation = self.create_quotation({self.shirt: 1}, order_type="Sales")

		self.assertEqual(cart.custom_code_order_discount, 9)
		self.assertFalse(desk_quotation.custom_code_order_discount)

	def test_a_discount_that_gives_nothing_does_not_block_another(self):
		self.create_discount(percentage=50, item_codes=(self.cap,), method="Automatic")
		code = self.create_code(percentage=10)

		quotation = self.create_quotation({self.shirt: 1}, (code,))

		self.assertEqual(quotation.custom_code_order_discount, 9)

	def test_a_prepaid_discount_drops_off_for_cash_on_delivery(self):
		code = self.create_code(percentage=10, payment_condition="Prepaid")
		quotation = self.create_quotation({self.shirt: 1}, (code,))
		self.assertEqual(quotation.custom_code_order_discount, 9)

		quotation.flags.commera_payment_kind = "cod"
		refresh_code_discounts(quotation)

		self.assertFalse(quotation.custom_code_order_discount)

	def test_a_customer_group_discount_skips_other_groups(self):
		group = frappe.get_doc(
			{"doctype": "Customer Group", "customer_group_name": f"ZZ VIP {frappe.generate_hash(length=6)}"}
		).insert(ignore_permissions=True)
		code = self.create_code(
			percentage=10, eligibility="Customer Groups", customer_groups=[{"customer_group": group.name}]
		)

		member = self.create_quotation({self.shirt: 1}, (code,), customer=self.create_customer(group.name))
		other = self.create_quotation({self.shirt: 1}, (code,))

		self.assertEqual(member.custom_code_order_discount, 9)
		self.assertFalse(other.custom_code_order_discount)

	def test_a_first_order_discount_skips_a_returning_customer(self):
		code = self.create_code(percentage=10, eligibility="First Order")
		first = self.create_quotation({self.shirt: 1}, (code,))
		self.assertEqual(first.custom_code_order_discount, 9)
		self.place_order(first)

		second = self.create_quotation({self.shirt: 1}, (code,))

		self.assertFalse(second.custom_code_order_discount)

	def test_a_once_per_customer_code_is_not_applied_twice(self):
		code = self.create_code(percentage=10, once_per_customer=1)
		self.place_order(self.create_quotation({self.shirt: 1}, (code,)))

		second = self.create_quotation({self.shirt: 1}, (code,))

		self.assertFalse(second.custom_code_order_discount)

	def test_a_generated_code_is_used_once(self):
		discount = self.create_discount(percentage=10)
		first_code, second_code = generate_codes(discount, 2, prefix="zz-")
		self.place_order(self.create_quotation({self.shirt: 1}, (first_code,)))

		with self.assertRaises(DiscountCodeError):
			validate_new_discount_code(first_code, [])
		self.assertEqual(validate_new_discount_code(second_code, []), second_code)
		self.assertTrue(first_code.startswith("ZZ-"))

	def test_a_shipping_discount_frees_cheap_delivery_options(self):
		self.create_discount(
			discount_type="Free Shipping",
			method="Automatic",
			minimum_requirement="Subtotal",
			minimum_subtotal=50,
			maximum_shipping_rate=100,
			combines_with_product=1,
			combines_with_order=1,
		)
		quotation = self.create_quotation({self.shirt: 1})
		options = [{"title": "Standard", "amount": 60}, {"title": "Express", "amount": 150}]

		standard, express = apply_shipping_discounts(quotation, options)

		self.assertEqual((standard["amount"], standard["original_amount"]), (0, 60))
		self.assertEqual(express["amount"], 150)

	def test_checkout_removes_a_used_up_code_and_says_why(self):
		frappe.db.set_value("Commera Discount", {"method": "Automatic"}, "enabled", 0)
		code = self.create_code(amount=10, usage_limit=1)
		quotation = self.create_quotation({self.shirt: 1}, (code,))
		self.place_order(self.create_quotation({self.shirt: 1}, (code,)))

		# The removal is committed before the message; a test must not commit its fixtures.
		with (
			patch.object(frappe.db, "commit"),
			self.assertRaisesRegex(CheckoutPriceChangedError, r"has been used up\. We removed"),
		):
			drop_refused_codes(quotation)

		quotation.reload()
		self.assertFalse(quotation.custom_discount_codes)
		self.assertEqual(quotation.net_total, SHIRT_RATE)

	def test_free_shipping_follows_how_the_order_is_paid(self):
		for payment_condition, shipping, cod_shipping in (("Prepaid", 0, 60), ("Cash On Delivery", 60, 0)):
			with self.subTest(payment_condition):
				frappe.db.set_value("Commera Discount", {"method": "Automatic"}, "enabled", 0)
				self.create_discount(
					discount_type="Free Shipping",
					method="Automatic",
					payment_condition=payment_condition,
					shipping_percentage=100,
				)
				quotation = self.create_quotation({self.shirt: 1})
				option = {"title": "Standard", "amount": 60}
				apply_delivery_option(quotation, apply_shipping_discounts(quotation, [option])[0])

				summary = get_checkout_summary(quotation)

				self.assertEqual(summary["shipping"], shipping)
				self.assertEqual(summary["cash_on_delivery"]["shipping"], cod_shipping)


class TestDiscountsOnOrders(DiscountCodeTestCase):
	def test_the_sales_order_keeps_discounts_and_logs_their_use(self):
		product = self.create_code(percentage=10, item_codes=(self.shirt,), combines_with_order=1)
		order = self.create_code(amount=5, combines_with_product=1)
		quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, (product, order))

		sales_order = self.place_order(quotation)
		sales_order.submit()

		discount = frappe.get_doc("Commera Discount", get_code_discount(product))
		self.assertEqual(self.get_line(sales_order, self.shirt).rate, 81)
		self.assertEqual(sales_order.custom_code_order_discount, 5)
		self.assertEqual(sales_order.net_total, quotation.net_total)
		self.assertEqual((discount.times_used, discount.discount_given), (1, 9))
		self.assertEqual(frappe.db.get_value("Commera Discount Code", product, "times_used"), 1)

		sales_order.cancel()
		self.assertEqual(frappe.db.get_value("Commera Discount", discount.name, "times_used"), 0)

	def test_the_invoice_keeps_discounts_over_an_automatic_rule(self):
		"""ERPNext prices the invoice again; with an automatic rule on the line that drops an unhooked code."""
		self.create_automatic_rule(self.shirt, percentage=10)
		code = self.create_code(amount=5, item_codes=(self.shirt,))
		sales_order = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))
		sales_order.submit()

		sales_invoice = make_sales_invoice(sales_order.name)
		sales_invoice.insert(ignore_permissions=True)

		self.assertEqual(self.get_line(sales_invoice, self.shirt).rate, 90 - 9 - 5)
		self.assertEqual(sales_invoice.net_total, sales_order.net_total)

	def test_a_discount_changed_after_checkout_does_not_reprice_the_order(self):
		code = self.create_code(percentage=10)
		quotation = self.create_quotation({self.shirt: 1}, (code,))
		frappe.db.set_value("Commera Discount", get_code_discount(code), "value", 50)
		frappe.clear_document_cache("Commera Discount", get_code_discount(code))

		sales_order = self.place_order(quotation)
		self.assertEqual(quotation.net_total, 81)
		self.assertEqual(sales_order.net_total, 81)

		sales_order.save()
		self.assertEqual(sales_order.net_total, 81)

	def test_partial_invoices_add_up_to_the_order_discount(self):
		product = self.create_code(amount=9, item_codes=(self.shirt,), combines_with_order=1)
		order = self.create_code(amount=10, combines_with_product=1)
		sales_order = self.place_order(self.create_quotation({self.shirt: 2, self.cap: 1}, (product, order)))
		sales_order.submit()

		invoices = [
			self.create_invoice(sales_order, self.cap),
			self.create_invoice(sales_order, self.shirt, qty=1),
			self.create_invoice(sales_order, self.shirt, qty=1),
		]

		self.assertEqual([invoice.custom_code_order_discount for invoice in invoices], [1.98, 4.01, 4.01])
		self.assertEqual(self.get_line(invoices[1], self.shirt).rate, 81)
		self.assertEqual(sum(invoice.net_total for invoice in invoices), sales_order.net_total)

	def test_a_credit_note_keeps_the_invoice_rates_and_its_share_of_the_order_discount(self):
		product = self.create_code(amount=9, item_codes=(self.shirt,), combines_with_order=1)
		order = self.create_code(amount=10, combines_with_product=1)
		sales_order = self.place_order(self.create_quotation({self.shirt: 2, self.cap: 1}, (product, order)))
		sales_order.submit()
		sales_invoice = self.create_invoice(sales_order)

		cap_return = self.create_return(sales_invoice, self.cap)
		shirt_return = self.create_return(sales_invoice, self.shirt)

		self.assertEqual(self.get_line(shirt_return, self.shirt).rate, 81)
		self.assertEqual(cap_return.custom_code_order_discount, -1.98)
		self.assertEqual(shirt_return.custom_code_order_discount, -8.02)
		self.assertEqual(cap_return.net_total + shirt_return.net_total, -sales_invoice.net_total)

	def test_a_free_unit_is_refunded_at_what_was_paid(self):
		code = self.create_code(percentage=100, item_codes=(self.cap,))
		sales_order = self.place_order(self.create_quotation({self.shirt: 1, self.cap: 1}, (code,)))
		sales_order.submit()
		sales_invoice = self.create_invoice(sales_order)

		cap_return = self.create_return(sales_invoice, self.cap)

		self.assertEqual(cap_return.net_total, 0)

	def test_an_amended_order_cannot_reuse_a_code_another_order_used_up(self):
		for limit in ("single use", "once per customer", "usage limit"):
			with self.subTest(limit):
				discount = self.create_discount(
					amount=10, once_per_customer=int(limit == "once per customer"), usage_limit=1
				)
				code = (
					generate_codes(discount, 1)[0]
					if limit == "single use"
					else add_code(discount, f"zz{frappe.generate_hash(length=8)}")
				)
				cancelled = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))
				cancelled.submit()
				cancelled.cancel()
				reorder = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))
				self.assertEqual(reorder.custom_code_order_discount, 10)

				with self.assertRaisesRegex(frappe.ValidationError, "another order|used up"):
					self.amend(cancelled)

				reorder.delete()
				self.assertEqual(self.amend(cancelled).custom_code_order_discount, 10)

	def amend(self, sales_order):
		amended = frappe.copy_doc(sales_order)
		amended.amended_from = sales_order.name
		amended.docstatus = 0
		return amended.insert(ignore_permissions=True)

	def test_in_words_and_the_payment_schedule_follow_the_discounted_total(self):
		self.customer.db_set("payment_terms", self.create_payment_terms())
		code = self.create_code(amount=10)
		quotation = self.create_quotation({self.shirt: 2}, (code,))
		sales_order = self.place_order(quotation)
		sales_order.submit()
		sales_invoice = self.create_invoice(sales_order)

		for doc in (quotation, sales_order, sales_invoice):
			self.assertEqual(doc.grand_total, 170)
			self.assertEqual(doc.in_words, money_in_words(170, doc.currency))
		for doc in (quotation, sales_order, sales_invoice):
			self.assertEqual([row.payment_amount for row in doc.payment_schedule], [85, 85])

	def create_payment_terms(self) -> str:
		terms = []
		for credit_days in (0, 30):
			term = frappe.get_doc(
				{
					"doctype": "Payment Term",
					"payment_term_name": f"ZZ {frappe.generate_hash(length=8)}",
					"invoice_portion": 50,
					"due_date_based_on": "Day(s) after invoice date",
					"credit_days": credit_days,
				}
			).insert(ignore_permissions=True)
			terms.append({"payment_term": term.name, "invoice_portion": 50, "credit_days": credit_days})
		return (
			frappe.get_doc(
				{
					"doctype": "Payment Terms Template",
					"template_name": f"ZZ Half Now {frappe.generate_hash(length=8)}",
					"terms": terms,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def create_invoice(self, sales_order, item_code: str | None = None, qty: int | None = None):
		sales_invoice = make_sales_invoice(sales_order.name)
		if item_code:
			sales_invoice.items = [item for item in sales_invoice.items if item.item_code == item_code]
		if qty:
			sales_invoice.items[0].qty = qty
		sales_invoice.insert(ignore_permissions=True)
		sales_invoice.submit()
		return sales_invoice

	def create_return(self, sales_invoice, item_code: str):
		credit_note = make_return_doc("Sales Invoice", sales_invoice.name)
		credit_note.items = [item for item in credit_note.items if item.item_code == item_code]
		credit_note.insert(ignore_permissions=True)
		credit_note.submit()
		return credit_note
