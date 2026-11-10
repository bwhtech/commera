from unittest.mock import patch

import frappe

from commera.localization.market_prices import MarketPrices
from commera.sdk import cart as cart_sdk
from commera.sdk import catalog, wishlist
from commera.tests.test_market_prices import MarketPriceTestCase


def get_customer():
	customer = frappe.db.get_value("Customer", {"disabled": 0}, "name")
	if customer:
		return customer
	doc = {"doctype": "Customer", "customer_name": f"Price Rules {frappe.generate_hash(length=6)}"}
	return frappe.get_doc(doc).insert(ignore_permissions=True).name


class TestCustomerPricesStayPrivate(MarketPriceTestCase):
	"""A customer's negotiated rate is never what an anonymous shopper sees or pays."""

	def setUp(self):
		super().setUp()
		self.customer = get_customer()

	def make_customer_price(self, item_code, price_list, rate):
		item_price = frappe.new_doc("Item Price")
		item_price.update(
			{
				"item_code": item_code,
				"price_list": price_list,
				"price_list_rate": rate,
				"customer": self.customer,
			}
		)
		return item_price.insert().name

	def test_a_market_customer_rate_is_not_the_public_price(self):
		route = self.make_market_variant("CUSTOMER", market_sale=300)
		item_code = self.get_item_code(route)
		self.make_customer_price(item_code, self.market_sale, 17)
		name = frappe.db.get_value("Style Attribute Variant", {"route": route})

		with self.in_market(), patch.object(catalog, "get_product_list", self.list_only([name])):
			product = catalog.get_product(route)
			card = catalog.list_products()["products"][0]
			item = catalog.get_items([item_code])[item_code]
			facet = catalog.get_market_price_facet()

		self.assertEqual((product["price"], card["price"], item["price"]), (300, 300, 300))
		self.assertEqual((facet["min"], facet["max"]), (300, 300))

	def test_a_customer_rate_alone_does_not_make_an_item_available(self):
		route = self.make_market_variant("CUSTOMERONLY")
		item_code = self.get_item_code(route)
		self.make_customer_price(item_code, self.market_sale, 17)

		with self.in_market():
			product = catalog.get_product(route)
			card = self.get_card(route)
			self.assertEqual(MarketPrices.current().get_unpriced([item_code]), {item_code})
			with self.assertRaisesRegex(frappe.ValidationError, "not available in this market"):
				cart_sdk.validate_items_for_sale([{"item_code": item_code, "qty": 1}])

		self.assertEqual((product["price"], product["available"]), (None, False))
		self.assertEqual((card["price"], card["available"]), (None, False))

	def test_the_primary_market_ignores_customer_rates_too(self):
		route = self.make_market_variant("CUSTOMERSTORE")
		self.make_customer_price(self.get_item_code(route), self.sale_price_list, 17)

		self.assertEqual(catalog.get_product(route)["price"], 80)
		self.assertEqual(self.get_card(route)["price"], 80)
		self.assertEqual(catalog.get_price_facet(self.sale_price_list), {"min": 80, "max": 80})


class TestCardAvailability(MarketPriceTestCase):
	def make_two_size_variant(self, label):
		"""Size M is priced in the market but has no stock; size L has stock but no market price."""
		priced = self.make_item(f"{label}-M")
		frappe.db.set_value("Item", priced, "is_stock_item", 1)
		unpriced = self.make_item(f"{label}-L")
		self.make_item_price(priced, self.market_sale, 300)
		self.make_item_price(unpriced, self.sale_price_list, 80)
		variant = self.make_variant(priced, f"cards-{label.lower()}-{self.suffix.lower()}")
		variant.append("sizes", {"size": "L", "item_code": unpriced})
		variant.save(ignore_permissions=True)
		return variant

	def test_a_card_needs_one_size_with_both_a_price_and_stock(self):
		variant = self.make_two_size_variant("SPLIT")

		with self.in_market():
			card = self.get_card(variant.route)

		self.assertEqual(card["price"], 300)
		self.assertFalse(card["available"])
		self.assertTrue(self.get_card(variant.route)["available"])

	def test_a_wishlist_card_needs_one_size_with_both_a_price_and_stock(self):
		variant = self.make_two_size_variant("WISH")
		wish = {"doctype": "Commera Wishlist Item", "user": frappe.session.user, "product": variant.name}
		frappe.get_doc(wish).insert(ignore_permissions=True)

		with self.in_market():
			cards = {card["id"]: card for card in wishlist.get_wishlist()["products"]}

		self.assertFalse(cards[variant.name]["available"])


class TestCartQuantityInMarket(MarketPriceTestCase):
	def make_cart(self, item_code, qty=1):
		cart = frappe.new_doc("Commera Cart")
		cart.append("lines", {"item_code": item_code, "qty": qty, "selected": 1})
		cart.lines[0].name = "line-1"
		cart.revision = 0
		# A saved cart: set_lines returns None for a new cart left empty.
		cart.set("__islocal", 0)
		return cart

	def change(self, cart, method, *args):
		with (
			patch.object(cart_sdk, "get_existing_cart", return_value=cart),
			patch.object(cart_sdk, "get_session_cart", return_value=cart),
			patch.object(cart_sdk, "get_open_cart_quotation", return_value=None),
			patch.object(cart_sdk, "save_server_cart", side_effect=lambda saved: saved),
		):
			return method(*args)

	def test_an_unpriced_line_cannot_grow_in_the_market(self):
		item_code = self.get_item_code(self.make_market_variant("CARTGROW"))

		with self.in_market():
			with self.assertRaisesRegex(frappe.ValidationError, "not available in this market"):
				self.change(
					self.make_cart(item_code), cart_sdk.update_lines, [{"line_id": "line-1", "qty": 2}]
				)
			with self.assertRaisesRegex(frappe.ValidationError, "not available in this market"):
				self.change(
					self.make_cart(item_code), cart_sdk.set_lines, [{"line_id": "line-1", "qty": 3}], 0
				)

	def test_an_unpriced_line_can_shrink_or_go(self):
		item_code = self.get_item_code(self.make_market_variant("CARTSHRINK"))

		with self.in_market():
			lowered = self.change(
				self.make_cart(item_code, qty=3), cart_sdk.update_lines, [{"line_id": "line-1", "qty": 1}]
			)
			kept = self.change(
				self.make_cart(item_code, qty=3), cart_sdk.set_lines, [{"line_id": "line-1", "qty": 3}], 0
			)
			dropped = self.change(self.make_cart(item_code), cart_sdk.set_lines, [], 0)

		self.assertEqual([row.qty for row in lowered.lines], [1])
		self.assertEqual([row.qty for row in kept.lines], [3])
		self.assertEqual(dropped.lines, [])

	def test_a_priced_line_grows_and_the_primary_market_is_unchanged(self):
		priced = self.get_item_code(self.make_market_variant("CARTPRICEDGROW", market_sale=300))
		unpriced = self.get_item_code(self.make_market_variant("CARTSTOREGROW"))

		with self.in_market():
			grown = self.change(
				self.make_cart(priced), cart_sdk.update_lines, [{"line_id": "line-1", "qty": 2}]
			)
		in_store = self.change(
			self.make_cart(unpriced), cart_sdk.update_lines, [{"line_id": "line-1", "qty": 2}]
		)

		self.assertEqual([row.qty for row in grown.lines], [2])
		self.assertEqual([row.qty for row in in_store.lines], [2])
