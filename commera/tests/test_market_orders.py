from unittest.mock import Mock, patch

import frappe
from erpnext.stock import get_item_details
from frappe.utils.data import add_days, today

from commera import item_price_guard
from commera.api.payment_hooks import on_payment_request_update
from commera.api.payments import (
	COD_PAYMENT_MODE,
	CheckoutPriceChangedError,
	_make_sales_order,
	confirm_payment,
	generate_quotation_for_cart,
	make_sales_invoice,
)
from commera.api.shipping import get_charge_amount
from commera.item_price_guard import install_guard, skip_auto_item_price
from commera.localization.markets import delete_cached_rows
from commera.sdk import cart as cart_sdk
from commera.tests.test_admin_orders import ensure_fiscal_year
from commera.tests.test_market_cart import MarketCartTestCase

GUARD_HOOK = "commera.item_price_guard.install_guard"
GATEWAY = "ZZ Market Gateway"


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


class TestPaidMarketOrders(MarketCartTestCase):
	"""A gateway-paid order: the webhook runs outside any market, after the shopper paid."""

	def setUp(self):
		super().setUp()
		ensure_fiscal_year()
		use_company_warehouse(self)
		mode_of_payment = {"doctype": "Mode of Payment", "mode_of_payment": GATEWAY, "type": "Bank"}
		frappe.get_doc(mode_of_payment).insert(ignore_permissions=True, ignore_if_duplicate=True)
		self.item_code = self.item("PAIDMARKET", market_sale=300)
		self.sign_in_shopper()
		self.add(self.item_code)
		with self.in_market():
			self.quotation = generate_quotation_for_cart({})
		frappe.set_user("Administrator")

	def test_a_line_withdrawn_after_payment_is_placed_at_its_paid_rate_with_a_note(self):
		frappe.db.delete("Item Price", {"item_code": self.item_code, "price_list": self.market_sale})

		sales_order = self.pay()

		self.assertEqual((sales_order.commera_market, sales_order.currency), ("gulf", self.currency))
		self.assertEqual((sales_order.items[0].rate, sales_order.docstatus), (300, 1))
		self.assertIn("Placed at paid rates; Gulf no longer prices", self.get_note(sales_order))

	def test_an_order_from_a_deleted_market_is_placed_with_a_note(self):
		# A market deleted before deletion was refused while orders and carts used it.
		frappe.db.delete("Commera Market", "gulf")
		delete_cached_rows()

		sales_order = self.pay()

		self.assertEqual((sales_order.items[0].rate, sales_order.docstatus), (300, 1))
		self.assertIn("market gulf no longer exists", self.get_note(sales_order))

	def test_an_order_its_market_still_sells_gets_no_note(self):
		self.assertIsNone(self.get_note(self.pay()))

	def test_a_charge_that_does_not_match_the_cart_is_still_refused(self):
		quotation = frappe.get_doc("Quotation", self.quotation.name)
		with self.assertRaisesRegex(frappe.ValidationError, "reconcile or refund the payment"):
			on_payment_request_update(self.make_payment_request(quotation, amount=250))

		self.assertEqual(frappe.db.get_value("Quotation", quotation.name, "docstatus"), 0)

	def pay(self):
		quotation = frappe.get_doc("Quotation", self.quotation.name)
		payment_request = self.make_payment_request(quotation, get_charge_amount(quotation))
		# Billing needs a gateway Mode of Payment; placement is what this tests.
		with patch("commera.api.payments.create_sales_invoice") as create_sales_invoice:
			on_payment_request_update(payment_request)
		create_sales_invoice.assert_called_once()
		return frappe.get_doc("Sales Order", payment_request.db_set.call_args.args[0]["ref_docname"])

	def make_payment_request(self, quotation, amount):
		payment_request = frappe._dict(
			status="Paid",
			ref_doctype="Quotation",
			ref_docname=quotation.name,
			gateway=GATEWAY,
			amount=amount,
			currency_code=quotation.currency,
			order_ref="pi_zz_market",
		)
		payment_request.db_set = Mock()
		return payment_request

	def get_note(self, sales_order):
		filters = {"reference_doctype": "Sales Order", "reference_name": sales_order.name}
		return frappe.db.get_value("Comment", {**filters, "comment_type": "Comment"}, "content")


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
		install_guard()
		self.set_single("Stock Settings", "auto_insert_price_list_rate_if_missing", 1)
		use_company_warehouse(self)
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


class TestItemPriceGuardInstall(MarketCartTestCase):
	"""A fresh process: ERPNext's insert is not wrapped until a hook or Commera's pricing wraps it."""

	def setUp(self):
		super().setUp()
		self.set_single("Stock Settings", "auto_insert_price_list_rate_if_missing", 1)
		wrapped, installed = get_item_details.insert_item_price, item_price_guard._installed
		self.addCleanup(self.restore_guard, wrapped, installed)
		self.original = getattr(wrapped, "__wrapped__", wrapped)
		self.restore_guard(self.original, False)
		self.item_code = self.get_item_code(self.make_priced_variant("GUARDINSTALL", default_rate=100))

	def test_the_request_and_job_hooks_install_the_guard(self):
		for hook in ("before_request", "before_job"):
			with self.subTest(hook=hook):
				self.restore_guard(self.original, False)
				self.assertIn(GUARD_HOOK, frappe.get_hooks(hook))
				frappe.call(GUARD_HOOK)
				self.assertTrue(get_item_details.insert_item_price.skips_cart_lines)

	def test_cart_pricing_inserts_no_price_and_other_pricing_does(self):
		ctx = self.get_pricing_context()

		with skip_auto_item_price():
			get_item_details.insert_item_price(ctx)
		self.assertFalse(self.has_sale_price())
		get_item_details.insert_item_price(ctx)
		self.assertTrue(self.has_sale_price())

	def restore_guard(self, insert_item_price, installed):
		get_item_details.insert_item_price = insert_item_price
		item_price_guard._installed = installed

	def get_pricing_context(self):
		# A line of an ordinary sales document: ERPNext adds its rate to the price list.
		return frappe._dict(
			item_code=self.item_code,
			price_list=self.sale_price_list,
			currency=self.store_currency,
			price_list_rate=90,
			rate=90,
			stock_uom=frappe.db.get_value("Item", self.item_code, "stock_uom"),
			conversion_factor=1,
			order_type="Sales",
			transaction_date=today(),
		)

	def has_sale_price(self):
		return frappe.db.exists(
			"Item Price", {"item_code": self.item_code, "price_list": self.sale_price_list}
		)


def use_company_warehouse(test):
	# Orders need a warehouse of the cart's company; the base case takes any.
	company = frappe.db.get_single_value("Commera Settings", "company") or frappe.defaults.get_global_default(
		"company"
	)
	test.warehouse = frappe.db.get_value("Warehouse", {"company": company, "is_group": 0})
	test.set_single("Commera Settings", "ecommerce_warehouse", test.warehouse)
