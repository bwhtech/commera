import frappe
from frappe.utils.data import add_days, today

from commera.api.payments import (
	COD_PAYMENT_MODE,
	CheckoutPriceChangedError,
	_make_sales_order,
	confirm_payment,
	generate_quotation_for_cart,
	make_sales_invoice,
	place_order,
	validate_paid_order_market,
)
from commera.sdk import cart as cart_sdk
from commera.tests.test_admin_orders import ensure_fiscal_year
from commera.tests.test_market_cart import MarketCartTestCase


class TestMarketOrderPlacement(MarketCartTestCase):
	def setUp(self):
		super().setUp()
		self.set_single("Commera Settings", "cod_enabled", 1)

	def test_a_cod_confirmation_refuses_a_cart_priced_in_another_market(self):
		item_code = self.item("CODSWITCH", market_sale=300)
		self.sign_in_shopper()
		self.add(item_code)
		quotation = generate_quotation_for_cart({})

		with self.in_market(), self.assertRaises(CheckoutPriceChangedError):
			confirm_payment(quotation.name, payment_mode=COD_PAYMENT_MODE)

		self.assertEqual(frappe.db.get_value("Quotation", quotation.name, "docstatus"), 0)

	def test_a_cod_confirmation_refuses_a_line_the_market_does_not_price(self):
		priced_there = self.item("CODPRICED", market_sale=300)
		route = self.make_market_variant("CODUNPRICED")
		self.sign_in_shopper()
		self.add(priced_there, self.get_item_code(route))

		with self.in_market():
			quotation = generate_quotation_for_cart({})
			with self.assertRaisesRegex(frappe.ValidationError, f"Display {route} - M is not available"):
				confirm_payment(quotation.name, payment_mode=COD_PAYMENT_MODE)

		self.assertEqual(frappe.db.get_value("Quotation", quotation.name, "docstatus"), 0)

	def test_a_paid_order_is_checked_in_the_market_it_was_priced_in(self):
		item_code = self.item("PAIDMARKET", market_sale=300)
		self.sign_in_shopper()
		self.add(item_code)
		with self.in_market():
			quotation = generate_quotation_for_cart({})
		frappe.set_user("Administrator")

		# The webhook's request is in the primary market: the quotation's own market decides.
		validate_paid_order_market(quotation)
		frappe.db.delete("Item Price", {"item_code": item_code, "price_list": self.market_sale})
		with self.assertRaisesRegex(frappe.ValidationError, "reconcile or refund the payment"):
			place_order(quotation, payment_mode="Stripe", gateway_amount=300)

		self.assertEqual(frappe.db.get_value("Quotation", quotation.name, "docstatus"), 0)


class TestMarketSaleExclusions(MarketCartTestCase):
	def test_a_code_that_skips_sale_items_reads_the_cart_market_lists(self):
		# On sale in the store only, and in the Gulf market only.
		store_sale = self.item("EXCLSTORE", market_compare_at=400)
		gulf_sale = self.get_item_code(self.make_priced_variant("EXCLGULF", default_rate=100))
		self.make_item_price(gulf_sale, self.market_sale, 300)
		self.make_item_price(gulf_sale, self.market_compare_at, 400)
		code = self.make_code(store_sale, gulf_sale, exclude_sale_items=1)
		self.sign_in_shopper()
		self.add(store_sale, gulf_sale)

		in_store = cart_sdk.add_discount_code(code)
		with self.in_market():
			in_market = cart_sdk.get_priced_cart()

		self.assertEqual(in_store["discounts"], [{"label": code, "amount": 10}])
		self.assertEqual(in_market["discounts"], [{"label": code, "amount": 40}])


class TestCartPriceInserts(MarketCartTestCase):
	"""ERPNext's "Auto insert Item Price" is on. A regular-only line has no sale-list price."""

	def setUp(self):
		super().setUp()
		self.set_single("Stock Settings", "auto_insert_price_list_rate_if_missing", 1)
		self.use_company_warehouse()
		self.regular_only = self.get_item_code(self.make_priced_variant("INSERTREGULAR", default_rate=100))
		self.sign_in_shopper()
		self.add(self.regular_only)
		self.quotation = generate_quotation_for_cart({})
		frappe.set_user("Administrator")

	def test_a_staff_rate_on_a_cart_order_survives_save(self):
		for ignore_pricing_rule in (0, 1):
			with self.subTest(ignore_pricing_rule=ignore_pricing_rule):
				sales_order = self.make_sales_order(ignore_pricing_rule)
				sales_order.items[0].rate = 75
				sales_order.save()

				line = sales_order.items[0]
				self.assertEqual((line.price_list_rate, line.rate, sales_order.total), (100, 75, 75))
		self.assertFalse(self.has_sale_price())

	def test_a_placed_and_billed_cart_order_adds_no_sale_price(self):
		ensure_fiscal_year()
		self.quotation.reload().submit()
		sales_order = _make_sales_order(self.quotation.name, ignore_permissions=True)
		sales_order.delivery_date = add_days(today(), 2)
		sales_order.insert().submit()
		sales_invoice = make_sales_invoice(sales_order.name).insert()

		self.assertEqual((sales_order.items[0].rate, sales_invoice.items[0].rate), (100, 100))
		self.assertFalse(self.has_sale_price())

	def use_company_warehouse(self):
		# Orders need a warehouse of the cart's company; the base case takes any.
		company = frappe.db.get_single_value(
			"Commera Settings", "company"
		) or frappe.defaults.get_global_default("company")
		self.warehouse = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0})
		self.set_single("Commera Settings", "ecommerce_warehouse", self.warehouse)

	def make_sales_order(self, ignore_pricing_rule):
		sales_order = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": self.quotation.party_name,
				"company": self.quotation.company,
				"order_type": "Shopping Cart",
				"selling_price_list": self.sale_price_list,
				"ignore_pricing_rule": ignore_pricing_rule,
				"delivery_date": add_days(today(), 2),
				"items": [
					{
						"item_code": self.regular_only,
						"qty": 1,
						"price_list_rate": 100,
						"rate": 100,
						"warehouse": self.warehouse,
					}
				],
			}
		)
		return sales_order.insert()

	def has_sale_price(self):
		return frappe.db.exists(
			"Item Price", {"item_code": self.regular_only, "price_list": self.sale_price_list}
		)
