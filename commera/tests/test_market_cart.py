import frappe
from frappe.utils.data import today

from commera.api.payments import (
	COD_PAYMENT_MODE,
	CheckoutPriceChangedError,
	generate_quotation_for_cart,
	open_checkout,
	save_cart_quotation,
	validate_cart_market,
)
from commera.commera_ecommerce.doctype.commera_cart.commera_cart import get_session_cart
from commera.core import _get_cart_quotation
from commera.discounts.codes import add_code
from commera.sdk import cart as cart_sdk
from commera.tests.test_market_prices import MarketPriceTestCase
from commera.www.cart.checkout import cart_needs_refresh


class MarketCartTestCase(MarketPriceTestCase):
	"""A shopper's cart. Store items sell at 80 (sale) from 100; Gulf items at their market rates."""

	def setUp(self):
		super().setUp()
		self.make_exchange_rate()
		self.addCleanup(frappe.set_user, "Administrator")

	def make_exchange_rate(self):
		# Named by date and currencies: an earlier test of the class may have made it.
		exchange = {
			"doctype": "Currency Exchange",
			"date": today(),
			"from_currency": self.currency,
			"to_currency": self.store_currency,
			"exchange_rate": 20,
			"for_selling": 1,
		}
		frappe.get_doc(exchange).insert(ignore_permissions=True, ignore_if_duplicate=True)

	def sign_in_shopper(self):
		user = {
			"doctype": "User",
			"email": f"zz-market-cart-{frappe.generate_hash(length=8)}@example.com",
			"first_name": "ZZ Market",
			"send_welcome_email": 0,
			"user_type": "Website User",
			"roles": [{"role": "Customer"}],
		}
		frappe.set_user(frappe.get_doc(user).insert(ignore_permissions=True).name)

	def item(self, label, **market_rates):
		return self.get_item_code(self.make_market_variant(label, **market_rates))

	def add(self, *item_codes):
		return cart_sdk.add_lines([{"item_code": item_code, "qty": 1} for item_code in item_codes])

	def lines(self, priced):
		return {line["item_code"]: line for line in priced["lines"]}

	def stored_cart(self):
		return frappe.db.get_value(
			"Commera Cart", get_session_cart().name, ["market", "discount_codes"], as_dict=True
		)


class TestCartPriceRule(MarketCartTestCase):
	def test_a_regular_only_line_sells_at_its_regular_rate_in_the_primary_market(self):
		regular_only = self.get_item_code(self.make_priced_variant("STOREREGULAR", default_rate=100))
		on_sale = self.item("STORESALE")
		self.sign_in_shopper()

		priced = self.add(regular_only, on_sale)

		lines = self.lines(priced)
		self.assertEqual((priced["market"], priced["currency"]), ("primary", self.store_currency))
		self.assertEqual((lines[regular_only]["price"], lines[regular_only]["rate"]), (100, 100))
		self.assertEqual((lines[on_sale]["price"], lines[on_sale]["rate"]), (80, 80))
		self.assertTrue(lines[regular_only]["available"] and lines[on_sale]["available"])
		self.assertEqual(priced["subtotal"], 180)

	def test_a_regular_only_line_sells_at_its_market_regular_rate(self):
		regular_only = self.item("GULFREGULAR", market_compare_at=400)
		on_sale = self.item("GULFSALE", market_sale=300, market_compare_at=400)
		self.sign_in_shopper()

		with self.in_market():
			priced = self.add(regular_only, on_sale)

		lines = self.lines(priced)
		self.assertEqual((priced["market"], priced["currency"]), ("gulf", self.currency))
		self.assertEqual(lines[regular_only]["rate"], 400)
		self.assertEqual((lines[on_sale]["price"], lines[on_sale]["rate"]), (300, 300))
		self.assertEqual(priced["subtotal"], 700)

	def test_an_item_in_neither_list_is_refused_by_product_and_size(self):
		route = self.make_priced_variant("NOPRICE", default_rate=None)
		store_unpriced = self.get_item_code(route)
		gulf_unpriced = self.item("GULFNOPRICE")
		self.sign_in_shopper()

		with self.assertRaises(frappe.ValidationError) as refused:
			self.add(store_unpriced)
		with self.in_market(), self.assertRaises(frappe.ValidationError) as refused_in_market:
			self.add(gulf_unpriced)

		self.assertIn(f"Display {route} - M is not available in this market", str(refused.exception))
		self.assertNotIn(store_unpriced, str(refused.exception))
		self.assertIn("is not available in this market", str(refused_in_market.exception))
		self.assertNotIn(gulf_unpriced, str(refused_in_market.exception))


class TestMarketSwitch(MarketCartTestCase):
	def test_a_switch_reprices_the_same_cart_and_flags_lines_the_market_does_not_price(self):
		priced_there = self.item("SWITCHPRICED", market_sale=300)
		not_priced_there = self.item("SWITCHUNPRICED")
		self.sign_in_shopper()
		cart_name = self.add(priced_there, not_priced_there)["name"]

		with self.in_market():
			priced = cart_sdk.get_priced_cart()

		lines = self.lines(priced)
		self.assertEqual(
			(priced["name"], priced["market"], priced["currency"]), (cart_name, "gulf", self.currency)
		)
		self.assertEqual((lines[priced_there]["rate"], lines[priced_there]["available"]), (300, True))
		self.assertEqual(
			(lines[not_priced_there]["amount"], lines[not_priced_there]["available"]), (0, False)
		)
		self.assertEqual(priced["subtotal"], 300)

	def test_a_read_saves_no_switch_and_the_next_change_does(self):
		item_code = self.item("SWITCHSAVE", market_sale=300)
		self.sign_in_shopper()
		self.add(item_code)

		frappe.form_dict["_country"] = "AE"
		self.addCleanup(frappe.form_dict.pop, "_country", None)
		frappe.local.request_cache.clear()
		self.assertEqual(cart_sdk.get_priced_cart()["currency"], self.currency)
		self.assertEqual(self.stored_cart().market, "primary")

		line_id = get_session_cart().lines[0].name
		cart_sdk.update_lines([{"line_id": line_id, "qty": 2}])

		self.assertEqual(self.stored_cart().market, "gulf")

	def test_a_code_that_takes_nothing_off_after_a_switch_is_dropped_with_its_reason(self):
		priced_there = self.item("CODEPRICED", market_sale=300)
		not_priced_there = self.item("CODEUNPRICED")
		kept = self.make_code(priced_there)
		dropped = self.make_code(not_priced_there)
		self.sign_in_shopper()
		self.add(priced_there, not_priced_there)
		cart_sdk.add_discount_code(kept)
		self.assertTrue(
			all(state["applied"] for state in cart_sdk.add_discount_code(dropped)["discount_codes"])
		)

		with self.in_market():
			priced = cart_sdk.get_priced_cart()
			self.assertEqual(self.stored_cart().discount_codes, f"{kept}\n{dropped}")
			cart_sdk.update_lines([{"line_id": get_session_cart().lines[0].name, "qty": 2}])

		states = {state["code"]: state for state in priced["discount_codes"]}
		self.assertTrue(states[kept]["applied"])
		self.assertFalse(states[kept]["removed"])
		self.assertEqual((states[dropped]["applied"], states[dropped]["removed"]), (False, True))
		self.assertIn("Nothing in your cart qualifies", states[dropped]["reason"])
		self.assertEqual(priced["discounts"], [{"label": kept, "amount": 30}])
		self.assertEqual(self.stored_cart().discount_codes, kept)

	def make_code(self, item_code):
		discount = {
			"doctype": "Commera Discount",
			"title": f"ZZ Market {frappe.generate_hash(length=6)}",
			"discount_type": "Amount Off Products",
			"applies_to": "Specific Products",
			"value_type": "Percentage",
			"value": 10,
			"currency": self.store_currency,
			"combines_with_product": 1,
			"targets": [{"role": "Applies To", "target_type": "Item", "target": item_code}],
		}
		name = frappe.get_doc(discount).insert(ignore_permissions=True).name
		return add_code(name, f"zz{frappe.generate_hash(length=8)}")


class TestMarketCheckout(MarketCartTestCase):
	def test_checkout_refuses_a_quotation_priced_in_another_market(self):
		item_code = self.item("CHECKOUTSWITCH", market_sale=300)
		self.sign_in_shopper()
		self.add(item_code)
		quotation = generate_quotation_for_cart({})

		with self.in_market():
			self.assertTrue(cart_needs_refresh(quotation))
			with self.assertRaises(CheckoutPriceChangedError):
				open_checkout(quotation, COD_PAYMENT_MODE)
			rebuilt = generate_quotation_for_cart({})

		self.assertEqual((rebuilt.name, rebuilt.currency), (quotation.name, self.currency))
		self.assertEqual(rebuilt.selling_price_list, self.market_sale)
		self.assertEqual((rebuilt.items[0].rate, rebuilt.total), (300, 300))

	def test_checkout_refuses_a_line_the_market_does_not_price(self):
		priced_there = self.item("CHECKOUTPRICED", market_sale=300)
		route = self.make_market_variant("CHECKOUTUNPRICED")
		self.sign_in_shopper()
		self.add(priced_there, self.get_item_code(route))

		with self.in_market():
			quotation = generate_quotation_for_cart({})
			with self.assertRaisesRegex(frappe.ValidationError, f"Display {route} - M is not available"):
				open_checkout(quotation, COD_PAYMENT_MODE)
			cart_sdk.remove_lines([get_session_cart().lines[1].name])
			validate_cart_market(generate_quotation_for_cart({}))

	def test_a_regular_only_line_keeps_its_rate_and_adds_no_sale_price(self):
		regular_only = self.get_item_code(self.make_priced_variant("CHECKOUTREGULAR", default_rate=100))
		self.set_auto_insert_prices(1)
		self.sign_in_shopper()
		self.add(regular_only)

		quotation = generate_quotation_for_cart({})
		save_cart_quotation(_get_cart_quotation())

		quotation.reload()
		self.assertEqual((quotation.items[0].price_list_rate, quotation.items[0].rate), (100, 100))
		self.assertEqual(quotation.total, 100)
		sale_rows = {"item_code": regular_only, "price_list": self.sale_price_list}
		self.assertFalse(frappe.db.exists("Item Price", sale_rows))

	def set_auto_insert_prices(self, value):
		previous = frappe.db.get_single_value("Stock Settings", "auto_insert_price_list_rate_if_missing")
		self.addCleanup(self.write_auto_insert_prices, previous)
		self.write_auto_insert_prices(value)

	def write_auto_insert_prices(self, value):
		frappe.db.set_single_value("Stock Settings", "auto_insert_price_list_rate_if_missing", value)
		frappe.clear_document_cache("Stock Settings", "Stock Settings")

	def test_the_primary_market_checkout_is_not_refused(self):
		item_code = self.item("CHECKOUTSTORE")
		self.sign_in_shopper()
		self.add(item_code)

		quotation = generate_quotation_for_cart({})

		validate_cart_market(quotation)
		self.assertEqual((quotation.currency, quotation.total), (self.store_currency, 80))
