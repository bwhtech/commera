import frappe
from frappe.auth import CookieManager
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.storefront.cart import add_lines, get_cart, get_checkout_url, open_checkout, update_lines
from commera.commera_ecommerce.doctype.commera_cart.commera_cart import get_session_cart
from commera.guest import CART_TOKEN_HEADER, GUEST_CART_COOKIE
from commera.sdk.types import CartLineProduct, PricedCart, PricedCartLine
from commera.tests.test_product_details import ProductDetailPriceTestCase


class TestStorefrontCart(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.set_user, "Administrator")
		self.route = self.make_priced_variant("CART", default_rate=40, sale_rate=30)
		self.item_code = frappe.db.get_value(
			"Color Size Item",
			{"parent": frappe.db.get_value("Style Attribute Variant", {"route": self.route})},
			"item_code",
		)
		frappe.get_doc(
			{"doctype": "Bin", "item_code": self.item_code, "warehouse": self.warehouse, "actual_qty": 10}
		).insert(ignore_permissions=True)
		self.token = frappe.generate_hash(length=32)
		self.send_token(self.token)

	def send_token(self, token: str, user: str = "Guest"):
		if not hasattr(frappe.local, "request"):
			self.addCleanup(delattr, frappe.local, "request")
		frappe.local.request = Request(
			EnvironBuilder(path="/", headers={CART_TOKEN_HEADER: token}).get_environ()
		)
		frappe.local.request_ip = "127.0.0.1"
		frappe.local.cookie_manager = CookieManager()
		frappe.set_user(user)

	def test_added_lines_carry_their_product(self):
		cart = add_lines([{"item_code": self.item_code, "qty": 2}])

		line = cart["lines"][0]
		self.assertEqual((line["qty"], line["rate"]), (2, 30))
		self.assertEqual(line["product"]["handle"], self.route)
		self.assertEqual(line["product"]["variant_title"], "M")
		self.assertEqual(cart["total_quantity"], 2)
		for result, shape in ((cart, PricedCart), (line, PricedCartLine), (line["product"], CartLineProduct)):
			self.assertEqual(set(result), shape.__required_keys__ | shape.__optional_keys__)

	def test_an_item_no_product_sells_is_refused(self):
		frappe.set_user("Administrator")
		unlisted = self.make_item("UNLISTED")
		self.send_token(self.token)

		with self.assertRaisesRegex(frappe.ValidationError, "is not for sale"):
			add_lines([{"item_code": unlisted, "qty": 1}])

	def test_a_zero_quantity_removes_the_line(self):
		line_id = add_lines([{"item_code": self.item_code, "qty": 1}])["lines"][0]["line_id"]

		cart = update_lines([{"line_id": line_id, "qty": 0}])

		self.assertEqual(cart["lines"], [])
		self.assertEqual(get_cart()["total_quantity"], 0)

	def test_a_checkout_code_binds_the_cart_to_the_browser_once(self):
		add_lines([{"item_code": self.item_code, "qty": 1}])
		code = get_checkout_url()["path"].split("code=")[1]
		self.send_token("unused-browser-token-0000000000000000")

		open_checkout(code)

		self.assertEqual(frappe.local.cookie_manager.cookies[GUEST_CART_COOKIE]["value"], self.token)
		self.assertEqual(frappe.local.response["location"], "/en/cart/checkout")
		open_checkout(code)
		self.assertEqual(frappe.local.response["location"], "/en/cart")

	def test_a_signed_in_shopper_gets_the_storefront_cart_in_their_account(self):
		add_lines([{"item_code": self.item_code, "qty": 3}])
		code = get_checkout_url()["path"].split("code=")[1]
		self.send_token("signed-in-browser-token-000000000000", user="Administrator")

		open_checkout(code)

		self.assertEqual(
			[(row.item_code, row.qty) for row in get_session_cart().lines], [(self.item_code, 3)]
		)

	def test_checkout_needs_a_cart(self):
		with self.assertRaises(frappe.DoesNotExistError):
			get_checkout_url()
