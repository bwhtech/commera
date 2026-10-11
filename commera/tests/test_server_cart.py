import frappe

from commera.api.payments import generate_quotation_for_cart
from commera.api.server_cart import sync_server_cart
from commera.commera_ecommerce.doctype.commera_cart.commera_cart import get_session_cart
from commera.sdk import cart as cart_sdk
from commera.tests.test_discount_codes import CAP_RATE, SHIRT_RATE, DiscountCodeTestCase


class TestServerCart(DiscountCodeTestCase):
	def setUp(self):
		super().setUp()
		sale_price_list = frappe.db.get_single_value("Commera Settings", "sale_price_list")
		self.addCleanup(self.set_sale_price_list, sale_price_list)
		self.set_sale_price_list(self.price_list)
		self.shopper = self.create_shopper()
		frappe.set_user(self.shopper)

	def set_sale_price_list(self, price_list: str):
		frappe.db.set_single_value("Commera Settings", "sale_price_list", price_list)
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

	def create_shopper(self) -> str:
		email = f"zz-cart-{frappe.generate_hash(length=8)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "ZZ Cart",
				"send_welcome_email": 0,
				"user_type": "Website User",
			}
		)
		user.append("roles", {"role": "Customer"})
		user.insert(ignore_permissions=True)
		return email

	def browser_line(self, item_code: str, qty: int) -> dict:
		return {"item": {"display_name": item_code}, "variant": {"item_code": item_code}, "qty": qty}

	def test_lines_merge_only_when_item_and_attributes_match(self):
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1, "attributes": {"engraving": "AB"}}])
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 2, "attributes": {"engraving": "AB"}}])

		priced = cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])

		self.assertEqual(
			[(line["qty"], line["attributes"]) for line in priced["lines"]],
			[(3, {"engraving": "AB"}), (1, {})],
		)

	def test_browser_quantities_keep_line_attributes(self):
		cart_sdk.add_lines(
			[
				{"item_code": self.shirt, "qty": 1, "attributes": {"gift": "yes"}},
				{"item_code": self.cap, "qty": 1},
			]
		)
		cart = get_session_cart()

		self.assertTrue(cart.set_quantities({self.shirt: 3}))

		self.assertEqual([(row.item_code, row.qty) for row in cart.lines], [(self.shirt, 3)])
		self.assertEqual(frappe.parse_json(cart.lines[0].attributes), {"gift": "yes"})

	def test_a_stale_browser_does_not_overwrite_the_server_cart(self):
		version = sync_server_cart([{"item_code": self.shirt, "qty": 1}])["version"]
		server_version = cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])["version"]

		response = sync_server_cart([{"item_code": self.shirt, "qty": 5}], version)

		self.assertTrue(response["conflict"])
		self.assertEqual(response["version"], server_version)
		self.assertEqual(
			{(row.item_code, row.qty) for row in get_session_cart().lines}, {(self.shirt, 1), (self.cap, 1)}
		)

	def test_the_priced_cart_shows_line_and_order_discounts(self):
		product = self.create_code(percentage=10, item_codes=(self.shirt,), combines_with_order=1)
		order = self.create_code(amount=10, combines_with_product=1)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 2}, {"item_code": self.cap, "qty": 1}])
		cart_sdk.add_discount_code(product.lower())

		priced = cart_sdk.add_discount_code(order)

		shirt = next(line for line in priced["lines"] if line["item_code"] == self.shirt)
		self.assertEqual((shirt["rate"], shirt["code_discount"], shirt["discount_code"]), (81, 9, product))
		self.assertEqual(priced["subtotal"], 2 * 81 + CAP_RATE)
		self.assertEqual(priced["order_discount"], 10)
		self.assertEqual(priced["total"], 2 * 81 + CAP_RATE - 10)

	def test_checkout_takes_attributes_and_codes_from_the_server_cart(self):
		code = self.create_code(amount=10, item_codes=(self.shirt,))
		cart_sdk.add_lines(
			[
				{"item_code": self.shirt, "qty": 1, "attributes": {"engraving": "AB"}},
				{"item_code": self.shirt, "qty": 1, "attributes": {"engraving": "CD"}},
			]
		)
		cart_sdk.add_discount_code(code)

		quotation = generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 2)]})

		self.assertEqual(
			[(row.qty, frappe.parse_json(row.custom_line_attributes)) for row in quotation.items],
			[(1, {"engraving": "AB"}), (1, {"engraving": "CD"})],
		)
		self.assertEqual({row.rate for row in quotation.items}, {SHIRT_RATE - 10})
		self.assertEqual(quotation.custom_discount_codes, code)

	def test_checkout_keeps_an_order_code_through_the_coupon_reset(self):
		"""Checkout zeroes the document discount after a save; the order code must still apply."""
		code = self.create_code(amount=10)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		cart_sdk.add_discount_code(code)

		quotation = generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 1)]})

		self.assertEqual(quotation.custom_code_order_discount, 10)
		self.assertEqual(quotation.net_total, SHIRT_RATE - 10)

	def test_checkout_without_a_server_cart_is_unchanged(self):
		quotation = generate_quotation_for_cart({"items": [self.browser_line(self.cap, 2)]})

		self.assertEqual(
			[(row.item_code, row.qty, row.rate) for row in quotation.items], [(self.cap, 2, CAP_RATE)]
		)
		self.assertFalse(quotation.custom_discount_codes)
