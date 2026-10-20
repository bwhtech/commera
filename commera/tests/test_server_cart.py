import frappe
from frappe.auth import CookieManager
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.payments import generate_quotation_for_cart
from commera.api.server_cart import apply_discount_code, remove_discount_code, sync_server_cart
from commera.commera_ecommerce.doctype.commera_cart.commera_cart import (
	MAX_LINE_QUANTITY,
	get_session_cart,
	keep_guest_cart,
)
from commera.core import _get_cart_quotation
from commera.discounts.codes import get_code_discount
from commera.guest import GUEST_CART_COOKIE
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

	def test_sync_refuses_more_than_the_stock(self):
		self.assertTrue(sync_server_cart([{"item_code": self.shirt, "qty": 10}])["version"])

		with self.assertRaisesRegex(frappe.ValidationError, "out of stock"):
			sync_server_cart([{"item_code": self.shirt, "qty": 11}])

	def test_a_cart_line_holds_a_limited_quantity(self):
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": MAX_LINE_QUANTITY}])

		with self.assertRaisesRegex(frappe.ValidationError, "at most"):
			cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])

	def test_sign_in_makes_the_guest_cart_the_account_cart(self):
		code = self.create_code(amount=10)
		self.use_guest_cart()
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		cart_sdk.add_discount_code(code)

		frappe.set_user(self.shopper)
		keep_guest_cart()

		cart = get_session_cart()
		self.assertEqual([(row.item_code, row.qty) for row in cart.lines], [(self.shirt, 1)])
		self.assertEqual(cart.discount_codes, code)
		self.assertIsNone(cart.cart_key)
		self.assertIn(GUEST_CART_COOKIE, frappe.local.cookie_manager.to_delete)

	def test_sign_in_merges_the_guest_cart_into_the_account_cart(self):
		code = self.create_code(amount=10)
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])
		account_cart = get_session_cart().name
		self.use_guest_cart()
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 2}])
		cart_sdk.add_discount_code(code)
		guest_cart = get_session_cart().name

		frappe.set_user(self.shopper)
		keep_guest_cart()

		cart = get_session_cart()
		self.assertEqual(cart.name, account_cart)
		self.assertEqual({(row.item_code, row.qty) for row in cart.lines}, {(self.cap, 1), (self.shirt, 2)})
		self.assertEqual(cart.discount_codes, code)
		self.assertFalse(frappe.db.exists("Commera Cart", guest_cart))

	def use_guest_cart(self):
		token = frappe.generate_hash(length=32)
		frappe.local.request = Request(
			EnvironBuilder(path="/", headers={"Cookie": f"{GUEST_CART_COOKIE}={token}"}).get_environ()
		)
		self.addCleanup(delattr, frappe.local, "request")
		frappe.local.cookie_manager = CookieManager()
		frappe.set_user("Guest")

	def test_the_priced_cart_shows_line_and_order_discounts(self):
		product = self.create_code(percentage=10, item_codes=(self.shirt,), combines_with_order=1)
		order = self.create_code(amount=10, combines_with_product=1)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 2}, {"item_code": self.cap, "qty": 1}])
		cart_sdk.add_discount_code(product.lower())

		priced = cart_sdk.add_discount_code(order)

		shirt = next(line for line in priced["lines"] if line["item_code"] == self.shirt)
		self.assertEqual((shirt["rate"], shirt["code_discount"]), (81, 9))
		self.assertEqual(shirt["discount"], get_code_discount(product))
		self.assertEqual([state["applied"] for state in priced["discount_codes"]], [True, True])
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

	def test_checkout_keeps_an_order_code(self):
		code = self.create_code(amount=10)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		cart_sdk.add_discount_code(code)

		quotation = generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 1)]})

		self.assertEqual(quotation.custom_code_order_discount, 10)
		self.assertEqual(quotation.net_total, SHIRT_RATE - 10)

	def test_a_code_applied_at_checkout_reaches_the_checkout(self):
		code = self.create_code(amount=10)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 1)]})

		response = apply_discount_code(code.lower())

		quotation = _get_cart_quotation()
		self.assertEqual(quotation.custom_discount_codes, code)
		self.assertEqual(quotation.net_total, SHIRT_RATE - 10)
		self.assertEqual(response["checkout_summary"]["discount_amount"], 10)

	def test_a_code_removed_at_checkout_leaves_the_checkout(self):
		code = self.create_code(amount=10)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		cart_sdk.add_discount_code(code)
		generate_quotation_for_cart({"items": [self.browser_line(self.shirt, 1)]})

		response = remove_discount_code(code)

		quotation = _get_cart_quotation()
		self.assertFalse(quotation.custom_discount_codes)
		self.assertEqual(quotation.net_total, SHIRT_RATE)
		self.assertEqual(response["checkout_summary"]["discount_amount"], 0)

	def test_a_code_that_does_not_apply_yet_says_why(self):
		code = self.create_code(percentage=10, minimum_requirement="Subtotal", minimum_subtotal=500)
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])

		state = cart_sdk.add_discount_code(code)["discount_codes"][0]

		self.assertFalse(state["applied"])
		self.assertIn("more to use", state["reason"])

	def test_a_code_with_nothing_to_discount_says_so(self):
		code = self.create_code(percentage=10, item_codes=(self.shirt,))
		cart_sdk.add_lines([{"item_code": self.cap, "qty": 1}])

		state = cart_sdk.add_discount_code(code)["discount_codes"][0]

		self.assertIn("Nothing in your cart qualifies", state["reason"])

	def test_a_deleted_or_renamed_code_drops_off_with_a_message(self):
		deleted = self.create_code(amount=10)
		renamed = self.create_code(amount=5, combines_with_order=1)
		frappe.db.set_value("Commera Discount", get_code_discount(deleted), "combines_with_order", 1)
		kept = self.create_code(amount=3, combines_with_order=1)
		cart_sdk.add_lines([{"item_code": self.shirt, "qty": 1}])
		cart_sdk.add_discount_code(deleted)
		cart_sdk.add_discount_code(renamed)
		frappe.set_user("Administrator")
		frappe.delete_doc("Commera Discount Code", deleted, force=True)
		frappe.rename_doc("Commera Discount Code", renamed, f"{renamed}NEW", force=True)
		frappe.set_user(self.shopper)

		priced = cart_sdk.get_priced_cart()

		self.assertEqual(
			[(state["code"], state["applied"]) for state in priced["discount_codes"]],
			[(deleted, False), (renamed, False)],
		)
		self.assertIn("no longer a valid", priced["discount_codes"][0]["reason"])
		self.assertEqual(priced["total"], SHIRT_RATE)

		priced = cart_sdk.add_discount_code(kept)

		self.assertEqual([state["code"] for state in priced["discount_codes"]], [kept])
		self.assertEqual(priced["total"], SHIRT_RATE - 3)

	def test_checkout_without_a_server_cart_is_unchanged(self):
		quotation = generate_quotation_for_cart({"items": [self.browser_line(self.cap, 2)]})

		self.assertEqual(
			[(row.item_code, row.qty, row.rate) for row in quotation.items], [(self.cap, 2, CAP_RATE)]
		)
		self.assertFalse(quotation.custom_discount_codes)
