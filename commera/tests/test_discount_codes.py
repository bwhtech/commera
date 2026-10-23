import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from frappe.tests import IntegrationTestCase
from frappe.utils.data import add_days, flt, money_in_words, today

# ERPNext moved its transaction mappers to a sibling `mapper` module; both layouts are in the wild.
try:
	from erpnext.selling.doctype.sales_order.mapper import make_delivery_note
	from erpnext.stock.doctype.delivery_note.mapper import (
		make_sales_invoice as make_sales_invoice_from_delivery_note,
	)
except ImportError:
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note
	from erpnext.stock.doctype.delivery_note.delivery_note import (
		make_sales_invoice as make_sales_invoice_from_delivery_note,
	)

from commera.api.payments import (
	CheckoutPriceChangedError,
	_make_sales_order,
	drop_refused_codes,
	make_sales_invoice,
)
from commera.api.shipping import apply_delivery_option, get_checkout_summary
from commera.core import new_cart_quotation
from commera.discounts.allocations import get_allocations
from commera.discounts.codes import add_code, generate_codes, get_code_discount
from commera.discounts.doctype.commera_discount.commera_discount import DiscountCodeError
from commera.discounts.pricing import (
	MAX_SEARCHED_SELECTIONS,
	get_combinations,
	get_saving,
	refresh_code_discounts,
)
from commera.discounts.selection import MAX_DISCOUNT_CODES, validate_new_discount_code
from commera.discounts.shipping import apply_shipping_discounts
from commera.discounts.usage import (
	DiscountLimitError,
	add_usage,
	record_discount_uses,
	validate_discount_limits,
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
		self.customer = self.create_customer()

	def set_charge_account_head(self):
		company = frappe.get_cached_doc("Commera Settings").get(
			"company"
		) or frappe.defaults.get_global_default("company")
		charge_account_head = frappe.db.get_value(
			"Account", {"company": company, "root_type": "Income", "is_group": 0}, "name"
		)
		frappe.db.set_single_value("Commera Settings", "charge_account_head", charge_account_head)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")
		self.addCleanup(frappe.clear_document_cache, "Commera Settings", "Commera Settings")

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

	def create_automatic_discount(self, percentage: float = 0, amount: float = 0, item_codes=(), **fields):
		# Rows live until the class rolls back, and an automatic discount would price every later cart.
		name = self.create_discount(percentage, amount, item_codes, method="Automatic", **fields)
		self.addCleanup(frappe.db.set_value, "Commera Discount", name, "enabled", 0)
		return name

	def create_code(self, percentage: float = 0, amount: float = 0, item_codes=(), **fields) -> str:
		discount = self.create_discount(percentage, amount, item_codes, **fields)
		return add_code(discount, f"zz{frappe.generate_hash(length=8)}")

	def create_quotation(
		self,
		lines: dict[str, int],
		codes=(),
		customer=None,
		order_type="Shopping Cart",
		taxes=(),
		email=None,
	):
		customer = customer or self.customer
		quotation = new_cart_quotation(
			customer, email or f"{customer.name.lower().replace(' ', '-')}@example.com"
		)
		quotation.order_type = order_type
		quotation.selling_price_list = self.price_list
		for item_code, qty in lines.items():
			quotation.append("items", {"item_code": item_code, "qty": qty, "warehouse": self.warehouse})
		for tax in taxes:
			quotation.append("taxes", tax)
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

	def add_tax(self, doc, rate: float):
		company = doc.company
		parent_account = frappe.get_all(
			"Account", {"company": company, "root_type": "Liability", "is_group": 1}, pluck="name", limit=1
		)[0]
		account = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": f"ZZ GST {frappe.generate_hash(length=6)}",
				"parent_account": parent_account,
				"company": company,
				"account_type": "Tax",
			}
		).insert(ignore_permissions=True)
		doc.set(
			"taxes",
			[
				{
					"charge_type": "On Net Total",
					"account_head": account.name,
					"rate": rate,
					"description": "GST",
				}
			],
		)
		doc.save(ignore_permissions=True)
		return doc

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
		self.assertEqual(shirt.custom_discount, get_code_discount(code))
		self.assertEqual(self.get_line(quotation, self.cap).rate, CAP_RATE)
		self.assertEqual(quotation.net_total, 2 * 81 + CAP_RATE)

	def test_the_best_product_code_wins_on_a_line(self):
		small = self.create_code(percentage=10, item_codes=(self.shirt,), combines_with_product=1)
		large = self.create_code(amount=20, item_codes=(self.shirt,), combines_with_product=1)

		quotation = self.create_quotation({self.shirt: 1}, (small, large))

		shirt = self.get_line(quotation, self.shirt)
		self.assertEqual(shirt.rate, 70)
		self.assertEqual(shirt.custom_discount, get_code_discount(large))

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

	def test_a_budget_split_over_units_never_overshoots(self):
		code = self.create_code(percentage=50, item_codes=(self.shirt,), budget=100.01)

		quotation = self.create_quotation({self.shirt: 3}, (code,))

		shirt = self.get_line(quotation, self.shirt)
		self.assertEqual(shirt.custom_code_discount, 33.33)
		self.assertLessEqual(sum(row["amount"] for row in get_allocations(quotation)), 100.01)

	def test_buy_x_get_y_on_thousands_of_units_is_quick(self):
		code = self.create_code(
			discount_type="Buy X Get Y",
			buy_value=1,
			get_quantity=1,
			targets=[
				{"role": "Buys", "target_type": "Item", "target": self.shirt},
				{"role": "Gets", "target_type": "Item", "target": self.shirt},
			],
		)

		started = time.monotonic()
		quotation = self.create_quotation({self.shirt: 5000}, (code,))

		self.assertLess(time.monotonic() - started, 5)
		self.assertEqual(self.get_line(quotation, self.shirt).amount, 2500 * SHIRT_RATE)

	def test_a_budget_caps_the_discount(self):
		code = self.create_code(percentage=50, item_codes=(self.shirt,), budget=20)

		quotation = self.create_quotation({self.shirt: 1}, (code,))

		self.assertEqual(self.get_line(quotation, self.shirt).rate, SHIRT_RATE - 20)

	def test_a_fixed_amount_comes_off_each_unit(self):
		code = self.create_code(amount=10, item_codes=(self.shirt,))

		quotation = self.create_quotation({self.shirt: 3}, (code,))

		self.assertEqual(self.get_line(quotation, self.shirt).rate, 80)
		self.assertEqual(quotation.net_total, 240)

	def test_a_fixed_amount_once_per_order_is_shared_by_line_value(self):
		code = self.create_code(
			amount=26, item_codes=(self.shirt, self.cap), fixed_applies_to="Once Per Order"
		)

		quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, (code,))

		self.assertEqual(self.get_line(quotation, self.shirt).rate, 72)
		self.assertEqual(self.get_line(quotation, self.cap).rate, 32)
		self.assertEqual(quotation.net_total, 104)

	def test_a_product_percentage_cap_is_shared_by_its_lines(self):
		code = self.create_code(percentage=50, item_codes=(self.shirt, self.cap), maximum_discount=26)

		quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, (code,))

		self.assertEqual(self.get_line(quotation, self.shirt).rate, 72)
		self.assertEqual(self.get_line(quotation, self.cap).rate, 32)

	def test_a_spend_tier_applies_from_exactly_its_minimum(self):
		code = self.create_code(
			percentage=1,
			tiered=1,
			tiers=[{"minimum_subtotal": 130, "value": 10}, {"minimum_subtotal": 131, "value": 20}],
		)

		quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, (code,))

		self.assertEqual(quotation.custom_code_order_discount, 13)

	def test_a_minimum_subtotal_applies_once_the_cart_reaches_it(self):
		code = self.create_code(percentage=10, minimum_requirement="Subtotal", minimum_subtotal=130)

		reached = self.create_quotation({self.shirt: 1, self.cap: 1}, (code,))
		short = self.create_quotation({self.shirt: 1}, (code,))

		self.assertEqual(reached.custom_code_order_discount, 13)
		self.assertFalse(short.custom_code_order_discount)

	def test_a_minimum_subtotal_comes_off_when_the_cart_drops_below_it(self):
		code = self.create_code(percentage=10, minimum_requirement="Subtotal", minimum_subtotal=130)
		quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, (code,))

		quotation.items = [row for row in quotation.items if row.item_code == self.shirt]
		quotation.save(ignore_permissions=True)

		self.assertFalse(quotation.custom_code_order_discount)
		self.assertEqual(quotation.net_total, SHIRT_RATE)

	def test_a_minimum_quantity_needs_enough_units(self):
		code = self.create_code(percentage=10, minimum_requirement="Quantity", minimum_quantity=3)

		short = self.create_quotation({self.cap: 2}, (code,))
		reached = self.create_quotation({self.cap: 3}, (code,))

		self.assertFalse(short.custom_code_order_discount)
		self.assertEqual(reached.custom_code_order_discount, 12)

	def test_buy_one_get_one_frees_half_the_units(self):
		code = self.create_code(
			discount_type="Buy X Get Y",
			buy_value=1,
			get_quantity=1,
			targets=[
				{"role": "Buys", "target_type": "Item", "target": self.shirt},
				{"role": "Gets", "target_type": "Item", "target": self.shirt},
			],
		)

		even = self.create_quotation({self.shirt: 4}, (code,))
		odd = self.create_quotation({self.shirt: 5}, (code,))

		self.assertEqual(self.get_line(even, self.shirt).amount, 2 * SHIRT_RATE)
		self.assertEqual(self.get_line(odd, self.shirt).amount, 3 * SHIRT_RATE)

	def test_buy_x_get_y_stops_at_its_uses_per_order(self):
		code = self.create_code(
			discount_type="Buy X Get Y",
			buy_value=1,
			get_quantity=1,
			uses_per_order=1,
			targets=[
				{"role": "Buys", "target_type": "Item", "target": self.shirt},
				{"role": "Gets", "target_type": "Item", "target": self.shirt},
			],
		)

		quotation = self.create_quotation({self.shirt: 6}, (code,))

		self.assertEqual(self.get_line(quotation, self.shirt).amount, 5 * SHIRT_RATE)

	def test_buy_x_get_y_can_give_a_percentage_off(self):
		code = self.create_code(
			discount_type="Buy X Get Y",
			buy_value=2,
			get_quantity=1,
			get_value_type="Percentage",
			get_value=50,
			targets=[
				{"role": "Buys", "target_type": "Item", "target": self.shirt},
				{"role": "Gets", "target_type": "Item", "target": self.cap},
			],
		)

		quotation = self.create_quotation({self.shirt: 2, self.cap: 1}, (code,))

		self.assertEqual(self.get_line(quotation, self.cap).rate, 20)

	def test_an_order_discount_skips_items_already_on_sale(self):
		settings = frappe.get_cached_doc("Commera Settings")
		self.set_price(self.shirt, settings.get_default_price_list(), 200)
		self.set_price(self.shirt, settings.get_sale_price_list(), 100)
		code = self.create_code(percentage=10, exclude_sale_items=1)

		quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, (code,))

		self.assertEqual(quotation.custom_code_order_discount, 4)

	def test_order_codes_come_off_the_subtotal_left_after_a_product_code(self):
		product = self.create_code(amount=10, item_codes=(self.shirt,), combines_with_order=1)
		percent = self.create_code(percentage=10, combines_with_product=1, combines_with_order=1)
		fixed = self.create_code(amount=5, combines_with_product=1, combines_with_order=1)

		quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, (product, percent, fixed))

		self.assertEqual(quotation.total, 120)
		self.assertEqual(quotation.custom_code_order_discount, 17)
		self.assertEqual(quotation.net_total, 103)

	def test_tax_is_charged_on_the_discounted_line(self):
		code = self.create_code(percentage=10, item_codes=(self.shirt,))

		quotation = self.add_tax(self.create_quotation({self.shirt: 1}, (code,)), rate=18)

		self.assertEqual(quotation.net_total, 81)
		self.assertEqual(flt(quotation.total_taxes_and_charges, 2), 14.58)
		self.assertEqual(flt(quotation.grand_total, 2), 95.58)

	def test_tax_is_charged_after_an_order_discount(self):
		code = self.create_code(percentage=10)

		quotation = self.add_tax(self.create_quotation({self.shirt: 1, self.cap: 1}, (code,)), rate=18)

		self.assertEqual(quotation.custom_code_order_discount, 13)
		self.assertEqual(flt(quotation.total_taxes_and_charges, 2), 21.06)
		self.assertEqual(flt(quotation.grand_total, 2), 138.06)
		self.assertEqual(flt(sum(flt(row.net_amount) for row in quotation.items), 2), 117)

	def test_a_desk_quotation_ignores_its_codes(self):
		code = self.create_code(percentage=10)

		quotation = self.create_quotation({self.shirt: 1}, (code,), order_type="Sales")

		self.assertFalse(quotation.custom_code_order_discount)
		self.assertEqual(quotation.net_total, SHIRT_RATE)


class TestDiscountSelection(DiscountCodeTestCase):
	def test_codes_combine_only_when_both_allow_it(self):
		product = self.create_code(percentage=10, item_codes=(self.shirt,), combines_with_order=1)
		strict_order = self.create_code(percentage=5)
		open_order = self.create_code(percentage=5, combines_with_product=1)

		with self.assertRaises(DiscountCodeError):
			validate_new_discount_code(strict_order, [product])
		self.assertEqual(validate_new_discount_code(open_order, [product]), open_order)

	def test_many_automatic_discounts_are_searched_within_a_bound(self):
		frappe.db.set_value("Commera Discount", {"method": "Automatic"}, "enabled", 0)
		self.addCleanup(frappe.db.set_value, "Commera Discount", {"method": "Automatic"}, "enabled", 0)
		for amount in range(1, 31):
			self.create_discount(amount=amount, method="Automatic")

		with patch("commera.discounts.pricing.get_saving", wraps=get_saving) as saving:
			quotation = self.create_quotation({self.shirt: 1})

		self.assertEqual(quotation.custom_code_order_discount, 30)
		self.assertLessEqual(saving.call_count, 2 * MAX_SEARCHED_SELECTIONS)

	def test_combinations_of_many_combinable_discounts_are_found_without_a_blow_up(self):
		discount = SimpleNamespace(can_combine_with=lambda other: True)
		selections = [SimpleNamespace(discount=discount) for _index in range(40)]

		started = time.monotonic()
		combinations = get_combinations(selections)

		self.assertLess(time.monotonic() - started, 1)
		self.assertEqual(combinations, [selections])

	def test_of_two_codes_that_do_not_combine_the_bigger_saving_applies(self):
		order = self.create_code(amount=10)
		product = self.create_code(percentage=15, item_codes=(self.shirt,))
		for codes in ((order, product), (product, order)):
			with self.subTest(codes):
				quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, codes)

				self.assertEqual(quotation.net_total, 116.5)
				self.assertEqual([row["code"] for row in get_allocations(quotation)], [product])

	def test_a_code_and_an_automatic_discount_keep_the_bigger_saving(self):
		code = self.create_code(amount=10)
		for percentage, net_total, wins in ((5, 120, "code"), (20, 104, "automatic")):
			with self.subTest(percentage):
				automatic = self.create_discount(percentage=percentage, method="Automatic")
				self.addCleanup(frappe.db.set_value, "Commera Discount", automatic, "enabled", 0)
				quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, (code,))
				frappe.db.set_value("Commera Discount", automatic, "enabled", 0)

				self.assertEqual(quotation.net_total, net_total)
				self.assertEqual(
					[row["discount"] for row in get_allocations(quotation)],
					[get_code_discount(code) if wins == "code" else automatic],
				)

	def test_on_an_equal_saving_the_code_applied_first_stays(self):
		first = self.create_code(amount=10)
		second = self.create_code(percentage=100, item_codes=(self.cap,), maximum_discount=10)
		for codes in ((first, second), (second, first)):
			with self.subTest(codes):
				quotation = self.create_quotation({self.shirt: 1, self.cap: 1}, codes)

				self.assertEqual(quotation.net_total, 120)
				self.assertEqual([row["code"] for row in get_allocations(quotation)], [codes[0]])

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
		self.create_automatic_discount(percentage=10)

		cart = self.create_quotation({self.shirt: 1})
		desk_quotation = self.create_quotation({self.shirt: 1}, order_type="Sales")

		self.assertEqual(cart.custom_code_order_discount, 9)
		self.assertFalse(desk_quotation.custom_code_order_discount)

	def test_a_discount_that_gives_nothing_does_not_block_another(self):
		self.create_automatic_discount(percentage=50, item_codes=(self.cap,))
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

	def test_a_customer_group_discount_skips_other_groups_and_guests(self):
		group = frappe.get_doc(
			{"doctype": "Customer Group", "customer_group_name": f"ZZ VIP {frappe.generate_hash(length=6)}"}
		).insert(ignore_permissions=True)
		code = self.create_code(
			percentage=10, eligibility="Customer Groups", customer_groups=[{"customer_group": group.name}]
		)

		member_customer = self.create_customer(group.name)
		member = self.create_quotation({self.shirt: 1}, (code,), customer=member_customer)
		other = self.create_quotation({self.shirt: 1}, (code,))
		guest = self.create_quotation({self.shirt: 1}, (code,), customer=member_customer)
		guest.custom_guest_cart_key = frappe.generate_hash(length=16)
		refresh_code_discounts(guest)

		self.assertEqual(member.custom_code_order_discount, 9.0)
		self.assertEqual(member.net_total, 81.0)
		self.assertFalse(other.custom_code_order_discount)
		self.assertFalse(guest.custom_code_order_discount)
		self.assertEqual(guest.net_total, 90.0)

	def test_a_specific_customers_discount_skips_other_customers_and_guests(self):
		frappe.db.set_value("Commera Discount", {"method": "Automatic"}, "enabled", 0)
		code = self.create_code(
			percentage=10, eligibility="Specific Customers", customers=[{"customer": self.customer.name}]
		)

		listed = self.create_quotation({self.shirt: 1}, (code,))
		unlisted = self.create_quotation({self.shirt: 1}, (code,), customer=self.create_customer())
		guest = self.create_quotation({self.shirt: 1}, (code,))
		guest.custom_guest_cart_key = frappe.generate_hash(length=16)
		refresh_code_discounts(guest)

		self.assertEqual(listed.custom_code_order_discount, 9.0)
		self.assertEqual(listed.net_total, 81.0)
		self.assertFalse(unlisted.custom_code_order_discount)
		self.assertEqual(unlisted.net_total, 90.0)
		self.assertFalse(guest.custom_code_order_discount)
		self.assertEqual(guest.net_total, 90.0)

	def test_an_active_specific_customers_discount_needs_a_customer(self):
		with self.assertRaisesRegex(frappe.ValidationError, "at least one customer"):
			self.create_discount(percentage=10, eligibility="Specific Customers", enabled=1)
		self.assertTrue(self.create_discount(percentage=10, eligibility="Specific Customers", enabled=0))

		with self.assertRaisesRegex(frappe.ValidationError, "at most 100 customers"):
			self.create_discount(
				percentage=10,
				eligibility="Specific Customers",
				customers=[{"customer": self.customer.name}] * 101,
			)

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
		self.create_automatic_discount(
			discount_type="Free Shipping",
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

	def test_a_shipping_code_that_excludes_order_discounts_never_stacks_with_one(self):
		self.set_charge_account_head()
		frappe.db.set_value("Commera Discount", {"method": "Automatic"}, "enabled", 0)
		self.create_discount(
			percentage=10, method="Automatic", combines_with_product=1, combines_with_shipping=1
		)
		code = self.create_code(
			discount_type="Free Shipping", payment_condition="Prepaid", shipping_percentage=100
		)
		quotation = self.create_quotation({self.shirt: 1}, (code,))
		option = {"title": "Standard", "amount": 60}
		apply_delivery_option(quotation, apply_shipping_discounts(quotation, [option])[0])
		quotation.save(ignore_permissions=True)

		summary = get_checkout_summary(quotation)

		self.assertEqual((summary["shipping"], summary["discount_amount"]), (0, 0))
		cash_on_delivery = summary["cash_on_delivery"]
		self.assertEqual((cash_on_delivery["shipping"], cash_on_delivery["discount_amount"]), (60, 9))

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
		self.set_charge_account_head()
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

	def test_an_unknown_code_is_refused(self):
		with self.assertRaisesRegex(DiscountCodeError, "is not a valid discount code"):
			validate_new_discount_code("ZZ-NO-SUCH-CODE", [])

	def test_a_code_already_on_the_cart_is_refused(self):
		code = self.create_code(percentage=10)

		with self.assertRaisesRegex(DiscountCodeError, "is already applied"):
			validate_new_discount_code(code.lower(), [code])

	def test_a_disabled_code_is_refused(self):
		code = self.create_code(percentage=10, enabled=0)

		with self.assertRaisesRegex(DiscountCodeError, "is not active"):
			validate_new_discount_code(code, [])

	def test_a_code_that_starts_later_is_not_active_yet(self):
		code = self.create_code(percentage=10, starts_on=add_days(today(), 1))

		with self.assertRaisesRegex(DiscountCodeError, "is not active yet"):
			validate_new_discount_code(code, [])

	def test_a_code_ending_today_still_works(self):
		code = self.create_code(percentage=10, starts_on=add_days(today(), -3), ends_on=today())

		self.assertEqual(validate_new_discount_code(code, []), code)
		self.assertEqual(self.create_quotation({self.shirt: 1}, (code,)).custom_code_order_discount, 9)

	def test_a_code_past_its_usage_limit_is_used_up(self):
		code = self.create_code(percentage=10, usage_limit=1)
		self.place_order(self.create_quotation({self.shirt: 1}, (code,)))

		with self.assertRaisesRegex(DiscountCodeError, "has been used up"):
			validate_new_discount_code(code, [])
		self.assertFalse(self.create_quotation({self.shirt: 1}, (code,)).custom_code_order_discount)

	def test_once_per_customer_also_matches_the_email_in_any_case(self):
		code = self.create_code(percentage=10, once_per_customer=1)
		self.place_order(self.create_quotation({self.shirt: 1}, (code,), email="zz-sam@example.com"))

		other_customer = self.create_customer()
		second = self.create_quotation(
			{self.shirt: 1}, (code,), customer=other_customer, email="ZZ-Sam@Example.com"
		)

		self.assertFalse(second.custom_code_order_discount)

	def test_a_customer_group_discount_reaches_its_sub_groups(self):
		parent = frappe.get_doc(
			{
				"doctype": "Customer Group",
				"customer_group_name": f"ZZ Trade {frappe.generate_hash(length=6)}",
				"is_group": 1,
			}
		).insert(ignore_permissions=True)
		child = frappe.get_doc(
			{
				"doctype": "Customer Group",
				"customer_group_name": f"ZZ Wholesale {frappe.generate_hash(length=6)}",
				"parent_customer_group": parent.name,
			}
		).insert(ignore_permissions=True)
		self.create_automatic_discount(
			percentage=15,
			eligibility="Customer Groups",
			customer_groups=[{"customer_group": parent.name}],
		)

		member = self.create_quotation({self.shirt: 2}, customer=self.create_customer(child.name))
		retail = self.create_quotation({self.shirt: 2})

		self.assertEqual(member.custom_code_order_discount, 27)
		self.assertFalse(retail.custom_code_order_discount)

	def test_a_shipping_discount_can_take_half_off(self):
		self.create_automatic_discount(
			discount_type="Free Shipping",
			shipping_percentage=50,
			combines_with_product=1,
			combines_with_order=1,
		)
		quotation = self.create_quotation({self.shirt: 1})

		[standard] = apply_shipping_discounts(quotation, [{"title": "Standard", "amount": 80}])

		self.assertEqual((standard["amount"], standard["original_amount"]), (40, 80))
		self.assertFalse(standard["is_free"])

	def test_free_shipping_stacks_with_an_automatic_order_discount_when_both_allow_it(self):
		self.create_automatic_discount(percentage=10, combines_with_shipping=1)
		self.create_automatic_discount(discount_type="Free Shipping", combines_with_order=1)
		quotation = self.create_quotation({self.shirt: 1})

		[standard] = apply_shipping_discounts(quotation, [{"title": "Standard", "amount": 80}])

		self.assertEqual(quotation.custom_code_order_discount, 9)
		self.assertTrue(standard["is_free"])


class TestDiscountCodeRules(DiscountCodeTestCase):
	def test_a_code_made_in_desk_is_kept_upper_case(self):
		discount = self.create_discount(amount=10)
		code = frappe.get_doc({"doctype": "Commera Discount Code", "code": " save10 ", "discount": discount})

		self.assertEqual(code.insert(ignore_permissions=True).name, "SAVE10")

	def test_a_code_with_a_space_or_too_long_is_refused(self):
		discount = self.create_discount(amount=10)
		for code in ("SAVE 10", "X" * 65, "  "):
			with self.subTest(code), self.assertRaisesRegex(frappe.ValidationError, "1 to 64"):
				frappe.get_doc(
					{"doctype": "Commera Discount Code", "code": code, "discount": discount}
				).insert(ignore_permissions=True)

	def test_an_automatic_discount_takes_no_code(self):
		discount = self.create_discount(amount=10, method="Automatic", enabled=0)

		with self.assertRaisesRegex(frappe.ValidationError, "Only a code discount"):
			add_code(discount, f"zz{frappe.generate_hash(length=8)}")

	def test_a_used_code_stays_with_its_discount(self):
		code = self.create_code(amount=10)
		self.place_order(self.create_quotation({self.shirt: 1}, (code,)))
		code_doc = frappe.get_doc("Commera Discount Code", code)
		code_doc.discount = self.create_discount(amount=20)

		with self.assertRaisesRegex(frappe.ValidationError, "stays with its discount"):
			code_doc.save(ignore_permissions=True)


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

	def test_a_placed_order_keeps_its_discount_use_whatever_happens_to_it_later(self):
		discount = self.create_discount(amount=10, usage_limit=5)
		code = generate_codes(discount, 1)[0]
		sales_order = self.place_order(self.create_quotation({self.shirt: 1, self.cap: 1}, (code,)))
		sales_order.submit()
		placed = self.get_usage(discount, code)

		sales_invoice = self.create_invoice(sales_order, self.shirt)
		self.create_return(sales_invoice, self.shirt)
		self.assertEqual(self.get_usage(discount, code), placed)
		self.assertEqual(placed, (1, 10, 1, [(sales_order.name, 10)]))

	def test_a_draft_order_edit_scales_the_order_discount_and_never_raises_it(self):
		code = self.create_code(amount=26)
		sales_order = self.place_order(self.create_quotation({self.shirt: 1, self.cap: 1}, (code,)))

		sales_order.items = [self.get_line(sales_order, self.shirt)]
		sales_order.save(ignore_permissions=True)
		self.assertEqual((sales_order.custom_code_order_discount, sales_order.net_total), (18, 72))

		sales_order.append("items", {"item_code": self.cap, "qty": 2, "warehouse": self.warehouse})
		sales_order.save(ignore_permissions=True)
		self.assertEqual((sales_order.custom_code_order_discount, sales_order.net_total), (26, 144))

	def test_a_draft_order_edit_drops_an_order_discount_whose_minimum_is_no_longer_met(self):
		for requirement in ({"minimum_subtotal": 100}, {"minimum_quantity": 2}):
			with self.subTest(requirement):
				code = self.create_code(
					amount=30,
					minimum_requirement="Subtotal" if "minimum_subtotal" in requirement else "Quantity",
					**requirement,
				)
				sales_order = self.place_order(self.create_quotation({self.shirt: 1, self.cap: 1}, (code,)))
				self.assertEqual(sales_order.net_total, 100)

				sales_order.items = [self.get_line(sales_order, self.shirt)]
				sales_order.save(ignore_permissions=True)

				self.assertEqual((sales_order.custom_code_order_discount, sales_order.net_total), (0, 90))
				self.assertEqual(get_allocations(sales_order), [])
				self.assertIn("no longer applies", str(frappe.message_log[-1]))

	def test_a_cancelled_order_keeps_its_discount_use(self):
		discount = self.create_discount(amount=10, usage_limit=5)
		code = generate_codes(discount, 1)[0]
		sales_order = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))
		sales_order.submit()
		sales_order.cancel()

		self.assertEqual(self.get_usage(discount, code), (1, 10, 1, [(sales_order.name, 10)]))
		reorder = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))
		self.assertEqual(reorder.custom_code_order_discount, 0)

		amended = self.amend(sales_order)
		self.assertEqual(amended.custom_code_order_discount, 10)
		self.assertEqual(self.get_usage(discount, code), (1, 10, 1, [(sales_order.name, 10)]))

	def test_a_deleted_order_keeps_its_discount_use(self):
		discount = self.create_discount(amount=10, usage_limit=5)
		code = generate_codes(discount, 1)[0]
		sales_order = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))

		frappe.delete_doc("Sales Order", sales_order.name, ignore_permissions=True)

		self.assertEqual(self.get_usage(discount, code), (1, 10, 1, [(sales_order.name, 10)]))

	def test_a_limit_used_up_between_checkout_and_placement_refuses_the_order(self):
		limits = {
			"single use": {"usage_limit": 0},
			"usage limit": {"usage_limit": 1},
			"once per customer": {"once_per_customer": 1},
			"budget": {"budget": 15},
		}
		for limit, fields in limits.items():
			with self.subTest(limit):
				discount = self.create_discount(amount=10, **fields)
				code = (
					generate_codes(discount, 1)[0]
					if limit == "single use"
					else add_code(discount, f"zz{frappe.generate_hash(length=8)}")
				)
				# Both carts were priced while the code was still unused, as two open checkouts are.
				first = self.create_quotation({self.shirt: 1}, (code,))
				second = self.create_quotation({self.shirt: 1}, (code,))
				self.assertEqual(second.custom_code_order_discount, 10)

				self.place_order(first)
				with self.assertRaises(DiscountLimitError):
					self.place_order(second)
				self.assertEqual(self.get_usage(discount, code)[0], 1)

	def test_a_duplicated_order_gets_no_discount_and_uses_nothing(self):
		discount = self.create_discount(amount=10)
		code = generate_codes(discount, 1)[0]
		sales_order = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))

		duplicate = frappe.copy_doc(sales_order)
		duplicate.insert(ignore_permissions=True)

		self.assertEqual((duplicate.custom_code_order_discount, duplicate.net_total), (0, SHIRT_RATE))
		self.assertEqual(get_allocations(duplicate), [])
		self.assertEqual(self.get_usage(discount, code), (1, 10, 1, [(sales_order.name, 10)]))

	def get_usage(self, discount: str, code: str) -> tuple:
		times_used, discount_given = frappe.db.get_value(
			"Commera Discount", discount, ["times_used", "discount_given"]
		)
		uses = frappe.get_all(
			"Commera Discount Use", filters={"discount": discount}, fields=["sales_order", "amount"]
		)
		code_times_used = frappe.db.get_value("Commera Discount Code", code, "times_used")
		return times_used, discount_given, code_times_used, [(use.sales_order, use.amount) for use in uses]

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

	def test_staff_add_goodwill_on_top_of_the_order_code(self):
		code = self.create_code(amount=10)
		sales_order = self.place_order(self.create_quotation({self.shirt: 2}, (code,)))
		self.assertEqual(sales_order.discount_amount, 10)

		sales_order.discount_amount = 5
		with self.assertRaisesRegex(frappe.ValidationError, "includes .*10.* from discount codes"):
			sales_order.save()

		sales_order.reload()
		sales_order.discount_amount = 15
		sales_order.save()
		self.assertEqual((sales_order.discount_amount, sales_order.custom_code_order_discount), (15, 10))
		self.assertEqual(sales_order.net_total, 2 * SHIRT_RATE - 15)

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

	def test_an_invoice_with_another_orders_lines_takes_only_its_orders_share(self):
		code = self.create_code(amount=26)
		discounted = self.place_order(self.create_quotation({self.shirt: 1, self.cap: 1}, (code,)))
		discounted.submit()
		plain = self.place_order(self.create_quotation({self.cap: 1}))
		plain.submit()

		sales_invoice = make_sales_invoice(discounted.name)
		sales_invoice.items = [self.get_line(sales_invoice, self.shirt)]
		other_line = make_sales_invoice(plain.name).items[0]
		sales_invoice.append("items", other_line.as_dict(no_default_fields=True))
		sales_invoice.insert(ignore_permissions=True)

		self.assertEqual(sales_invoice.custom_code_order_discount, 18)

	def test_two_discounted_orders_cannot_share_an_invoice(self):
		code = self.create_code(amount=10)
		first = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))
		second = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))
		first.submit()
		second.submit()

		sales_invoice = make_sales_invoice(first.name)
		sales_invoice.append(
			"items", make_sales_invoice(second.name).items[0].as_dict(no_default_fields=True)
		)

		with self.assertRaisesRegex(frappe.ValidationError, "separate"):
			sales_invoice.insert(ignore_permissions=True)

	def test_a_delivery_note_and_its_invoice_carry_the_delivered_share(self):
		code = self.create_code(amount=26)
		sales_order = self.place_order(self.create_quotation({self.shirt: 1, self.cap: 1}, (code,)))
		sales_order.submit()

		delivery_note = make_delivery_note(sales_order.name)
		delivery_note.items = [self.get_line(delivery_note, self.shirt)]
		delivery_note.items[0].allow_zero_valuation_rate = 1
		delivery_note.insert(ignore_permissions=True)
		self.assertEqual(delivery_note.custom_code_order_discount, 18)
		self.assertEqual(delivery_note.discount_amount, 18)
		allow_negative_stock = frappe.db.get_single_value("Stock Settings", "allow_negative_stock")
		self.addCleanup(
			frappe.db.set_single_value, "Stock Settings", "allow_negative_stock", allow_negative_stock
		)
		frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 1)
		delivery_note.submit()

		sales_invoice = make_sales_invoice_from_delivery_note(delivery_note.name)
		sales_invoice.insert(ignore_permissions=True)
		self.assertEqual((sales_invoice.custom_code_order_discount, sales_invoice.discount_amount), (18, 18))

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
				other_order = self.place_order(self.create_quotation({self.shirt: 1}))
				frappe.get_doc(
					{
						"doctype": "Commera Discount Use",
						"discount": discount,
						"code": code,
						"sales_order": other_order.name,
						"amount": 10,
						"customer": other_order.customer,
					}
				).insert(ignore_permissions=True)
				add_usage({discount: 10}, {code}, 0)

				with self.assertRaisesRegex(DiscountLimitError, "another order|used up"):
					self.amend(cancelled)

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

	def test_the_campaign_tags_the_order_and_the_account_books_the_discount(self):
		frappe.db.set_single_value("Selling Settings", "enable_discount_accounting", 1)
		campaign = frappe.get_doc(
			{"doctype": "UTM Campaign", "__newname": f"ZZ Campaign {frappe.generate_hash(length=6)}"}
		).insert(ignore_permissions=True)
		sales_order_company = frappe.get_cached_doc("Commera Settings").get("company")
		account = frappe.get_all(
			"Account",
			filters={"is_group": 0, "root_type": "Expense", "company": sales_order_company or ["is", "set"]},
			pluck="name",
			limit=1,
		)[0]
		code = self.create_code(
			percentage=10, item_codes=(self.shirt,), campaign=campaign.name, discount_account=account
		)
		sales_order = self.place_order(self.create_quotation({self.shirt: 1, self.cap: 1}, (code,)))
		sales_order.submit()

		sales_invoice = self.create_invoice(sales_order)

		self.assertEqual(
			(sales_order.utm_campaign, sales_invoice.utm_campaign), (campaign.name, campaign.name)
		)
		self.assertEqual(self.get_line(sales_invoice, self.shirt).discount_account, account)
		debit = frappe.get_all(
			"GL Entry", filters={"voucher_no": sales_invoice.name, "account": account}, pluck="debit"
		)
		self.assertEqual(sum(debit), 9)

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

	def test_cart_order_and_invoice_totals_agree(self):
		product = self.create_code(percentage=10, item_codes=(self.shirt,), combines_with_order=1)
		order = self.create_code(amount=13, combines_with_product=1)
		quotation = self.create_quotation({self.shirt: 2, self.cap: 1}, (product, order))
		sales_order = self.place_order(quotation)
		sales_order.submit()

		sales_invoice = make_sales_invoice(sales_order.name)
		sales_invoice.insert(ignore_permissions=True)

		self.assertEqual(quotation.net_total, 2 * 81 + CAP_RATE - 13)
		self.assertEqual(
			{flt(doc.net_total, 2) for doc in (quotation, sales_order, sales_invoice)},
			{2 * 81 + CAP_RATE - 13},
		)
		self.assertEqual(
			{flt(doc.grand_total, 2) for doc in (quotation, sales_order, sales_invoice)},
			{flt(quotation.grand_total, 2)},
		)
		self.assertEqual(self.get_line(sales_invoice, self.shirt).rate, 81)
		self.assertEqual(sales_invoice.custom_code_order_discount, 13)

	def test_saving_a_draft_order_again_keeps_one_discount_and_one_use(self):
		code = self.create_code(percentage=10)
		sales_order = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))

		sales_order.reload()
		sales_order.save(ignore_permissions=True)
		sales_order.reload()
		sales_order.save(ignore_permissions=True)

		self.assertEqual(sales_order.custom_code_order_discount, 9)
		self.assertEqual(sales_order.net_total, 81)
		self.assertEqual(frappe.db.count("Commera Discount Use", {"sales_order": sales_order.name}), 1)

	def test_an_amended_order_uses_its_discount_once(self):
		code = self.create_code(percentage=10)
		sales_order = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))
		sales_order.submit()
		sales_order.cancel()

		amended = frappe.copy_doc(sales_order)
		amended.docstatus = 0
		amended.amended_from = sales_order.name
		amended.insert(ignore_permissions=True)

		self.assertEqual(amended.custom_code_order_discount, 9)
		self.assertEqual(frappe.db.count("Commera Discount Use", {"discount": get_code_discount(code)}), 1)

	def test_the_invoice_keeps_a_discount_switched_off_after_the_order(self):
		code = self.create_code(amount=10, item_codes=(self.shirt,))
		sales_order = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))
		sales_order.submit()
		frappe.db.set_value("Commera Discount", get_code_discount(code), "enabled", 0)
		frappe.clear_document_cache("Commera Discount", get_code_discount(code))

		sales_invoice = make_sales_invoice(sales_order.name)
		sales_invoice.insert(ignore_permissions=True)

		self.assertEqual(self.get_line(sales_invoice, self.shirt).rate, SHIRT_RATE - 10)


class TestTaxInclusiveDiscounts(DiscountCodeTestCase):
	def setUp(self):
		super().setUp()
		self.leggings = self.create_item(2999)
		self.shorts = self.create_item(3399)

	def test_a_discount_takes_exactly_its_amount_off_a_tax_inclusive_price(self):
		cases = {
			"200 off the order": (self.create_code(amount=200), 6198),
			"10% off the order": (self.create_code(percentage=10), 5758.2),
			"10% off products": (
				self.create_code(percentage=10, item_codes=(self.leggings, self.shorts)),
				5758.2,
			),
			"150 off each product": (
				self.create_code(amount=150, item_codes=(self.leggings, self.shorts)),
				6098,
			),
			"buy leggings get shorts free": (
				self.create_code(
					discount_type="Buy X Get Y",
					buy_value=1,
					get_quantity=1,
					uses_per_order=1,
					targets=[
						{"role": "Buys", "target_type": "Item", "target": self.leggings},
						{"role": "Gets", "target_type": "Item", "target": self.shorts},
					],
				),
				2999,
			),
		}
		for case, (code, grand_total) in cases.items():
			with self.subTest(case):
				quotation = self.create_quotation(
					{self.leggings: 1, self.shorts: 1}, (code,), taxes=[self.get_inclusive_tax()]
				)
				sales_order = self.place_order(quotation)
				sales_order.submit()
				sales_invoice = self.create_invoice(sales_order)

				for doc in (quotation, sales_order, sales_invoice):
					self.assertEqual(doc.grand_total, grand_total)
					self.assertAlmostEqual(doc.net_total, grand_total / 1.18, delta=0.01)
					self.assertAlmostEqual(doc.total_taxes_and_charges, grand_total * 18 / 118, delta=0.01)

	def get_inclusive_tax(self) -> dict:
		company = frappe.get_cached_doc("Commera Settings").get(
			"company"
		) or frappe.defaults.get_global_default("company")
		return {
			"charge_type": "On Net Total",
			"description": "GST 18% included",
			"account_head": frappe.db.get_value(
				"Account",
				{"company": company, "root_type": "Liability", "account_type": "", "is_group": 0},
				"name",
			),
			"rate": 18,
			"included_in_print_rate": 1,
		}

	def create_invoice(self, sales_order):
		sales_invoice = make_sales_invoice(sales_order.name)
		sales_invoice.insert(ignore_permissions=True)
		sales_invoice.submit()
		return sales_invoice


class TestDiscountCurrency(DiscountCodeTestCase):
	def setUp(self):
		super().setUp()
		self.foreign = "EUR" if self.currency != "EUR" else "USD"
		self.set_exchange_rate(self.foreign, 80)

	def set_exchange_rate(self, currency: str, rate: float):
		filters = {"from_currency": currency, "to_currency": self.currency, "date": today(), "for_selling": 1}
		if name := frappe.db.exists("Currency Exchange", filters):
			frappe.db.set_value("Currency Exchange", name, "exchange_rate", rate)
		else:
			frappe.get_doc({"doctype": "Currency Exchange", **filters, "exchange_rate": rate}).insert(
				ignore_permissions=True
			)

	def test_a_fixed_amount_in_another_currency_is_converted_to_the_cart_currency(self):
		cases = {
			"1 off the order": (
				self.create_code(amount=1, currency=self.foreign),
				{self.shirt: 1, self.cap: 1},
				50,
			),
			"0.25 off each item": (
				self.create_code(amount=0.25, item_codes=(self.shirt,), currency=self.foreign),
				{self.shirt: 2},
				140,
			),
			"blank currency is the company's": (
				self.create_code(amount=10, currency=None),
				{self.shirt: 1},
				80,
			),
		}
		for case, (code, lines, net_total) in cases.items():
			with self.subTest(case):
				self.assertEqual(self.create_quotation(lines, (code,)).net_total, net_total)

	def test_uses_in_two_currencies_add_up_in_the_company_currency(self):
		discount = self.create_discount(amount=10, currency=None)
		code = add_code(discount, f"zz{frappe.generate_hash(length=8)}")
		sales_order = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))
		foreign_order = self.place_order(self.create_quotation({self.shirt: 1}, (code,)))
		foreign_order.currency, foreign_order.conversion_rate = self.foreign, 80
		foreign_order.base_grand_total = foreign_order.grand_total * 80
		frappe.db.delete("Commera Discount Use", {"sales_order": foreign_order.name})
		frappe.db.set_value(
			"Commera Discount",
			discount,
			{"times_used": 1, "discount_given": 10, "sales": sales_order.base_grand_total},
		)
		frappe.db.set_value("Commera Discount Code", code, "times_used", 1)
		record_discount_uses(foreign_order)

		self.assertEqual(
			frappe.db.get_value("Commera Discount", discount, ["times_used", "discount_given", "sales"]),
			(2, 810, sales_order.grand_total + foreign_order.grand_total * 80),
		)

	def test_a_budget_in_another_currency_is_used_up_by_orders_in_the_company_currency(self):
		code = self.create_code(amount=1, currency=self.foreign, budget=1.5)
		discounts = []
		for _index in range(3):
			sales_order = self.place_order(self.create_quotation({self.shirt: 1, self.cap: 1}, (code,)))
			discounts.append(sales_order.custom_code_order_discount)

		self.assertEqual(discounts, [80, 40, 0])
		self.assertEqual(
			frappe.db.get_value("Commera Discount", get_code_discount(code), "discount_given"), 120
		)

	def test_money_thresholds_in_another_currency_are_converted(self):
		minimum = self.create_code(
			percentage=10, currency=self.foreign, minimum_requirement="Subtotal", minimum_subtotal=2
		)
		self.assertEqual(self.create_quotation({self.shirt: 1, self.cap: 1}, (minimum,)).net_total, 130)
		self.assertEqual(self.create_quotation({self.shirt: 2}, (minimum,)).net_total, 162)

		tiered = self.create_code(
			percentage=1,
			currency=self.foreign,
			tiered=1,
			tiers=[{"minimum_subtotal": 1, "value": 5}, {"minimum_subtotal": 2, "value": 10}],
		)
		self.assertEqual(self.create_quotation({self.shirt: 1, self.cap: 1}, (tiered,)).net_total, 123.5)

		shipping = self.create_code(
			discount_type="Free Shipping",
			currency=self.foreign,
			shipping_percentage=100,
			maximum_shipping_rate=1,
		)
		quotation = self.create_quotation({self.shirt: 1}, (shipping,))
		options = [{"title": "Standard", "amount": 60}, {"title": "Express", "amount": 100}]
		self.assertEqual(
			[option["amount"] for option in apply_shipping_discounts(quotation, options)], [0, 100]
		)


def run_in_another_request(function):
	site, sites_path = frappe.local.site, frappe.local.sites_path
	errors = []

	def target():
		frappe.init(site, sites_path=sites_path)
		frappe.connect()
		try:
			function()
			frappe.db.commit()
		except Exception as error:
			errors.append(error)
		finally:
			frappe.destroy()

	thread = threading.Thread(target=target)
	thread.start()
	thread.join()
	if errors:
		raise errors[0]


class TestDiscountUsageAcrossRequests(IntegrationTestCase):
	"""Commits on purpose: another connection only sees committed rows. Everything made here is deleted."""

	def setUp(self):
		self.discount = (
			frappe.get_doc(
				{
					"doctype": "Commera Discount",
					"title": f"ZZ Race {frappe.generate_hash(length=6)}",
					"discount_type": "Amount Off Order",
					"value_type": "Fixed Amount",
					"value": 10,
					"usage_limit": 1,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.code = add_code(self.discount, f"zz{frappe.generate_hash(length=8)}")
		frappe.db.commit()
		self.addCleanup(self.delete_committed)

	def delete_committed(self):
		frappe.db.rollback()
		frappe.delete_doc("Commera Discount Code", self.code, ignore_permissions=True, force=True)
		frappe.delete_doc("Commera Discount", self.discount, ignore_permissions=True, force=True)
		frappe.db.commit()

	def test_a_placement_sees_a_use_another_request_committed_after_it_started(self):
		self.assertEqual(frappe.db.get_value("Commera Discount", self.discount, "times_used"), 0)

		run_in_another_request(lambda: add_usage({self.discount: 10}, {self.code}, 100))

		# This request's snapshot still says unused; only a locking read sees the other order.
		self.assertEqual(frappe.db.get_value("Commera Discount", self.discount, "times_used"), 0)
		with self.assertRaises(DiscountLimitError):
			validate_discount_limits(
				frappe.new_doc("Sales Order"), {(self.discount, self.code): 10}, {self.discount: 10}, []
			)

	def test_two_placements_committed_together_both_count(self):
		self.assertEqual(frappe.db.get_value("Commera Discount", self.discount, "times_used"), 0)

		run_in_another_request(lambda: add_usage({self.discount: 10}, {self.code}, 100))
		add_usage({self.discount: 10}, {self.code}, 100)

		self.assertEqual(
			frappe.db.get_value(
				"Commera Discount", self.discount, ["times_used", "discount_given", "sales"], for_update=True
			),
			(2, 20, 200),
		)
		self.assertEqual(
			frappe.db.get_value("Commera Discount Code", self.code, "times_used", for_update=True), 2
		)
