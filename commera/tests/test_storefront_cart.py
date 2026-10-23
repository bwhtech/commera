import time
from urllib.parse import parse_qs, urlsplit

import frappe
from frappe.auth import CookieManager
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.storefront.cart import (
	CHECKOUT_CODE_PREFIX,
	add_lines,
	adopt_cart,
	adopt_checkout_cart,
	claim_checkout_cart,
	get_cart,
	get_checkout_url,
	open_checkout,
	remove_lines,
	update_lines,
)
from commera.commera_ecommerce.doctype.commera_cart.commera_cart import get_session_cart
from commera.guest import CART_TOKEN_HEADER, GUEST_CART_COOKIE
from commera.sdk import cart as cart_sdk
from commera.sdk.types import CartLineProduct, PricedCart, PricedCartLine
from commera.tests.test_order_access import make_website_user
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
		# Every direct call shares one rate-limit counter for this IP, and it outlives the test.
		frappe.cache.delete_keys("rl:*127.0.0.1*")
		self.token = frappe.generate_hash(length=32)
		self.send_token(self.token)

	def send_token(
		self,
		token: str | None,
		user: str = "Guest",
		path: str = "/api/method/commera.api.storefront.cart.get_cart",
	):
		if not hasattr(frappe.local, "request"):
			self.addCleanup(delattr, frappe.local, "request")
		headers = {CART_TOKEN_HEADER: token} if token else {}
		frappe.local.request = Request(EnvironBuilder(path=path, headers=headers).get_environ())
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

	def test_a_template_item_is_refused(self):
		frappe.set_user("Administrator")
		template = self.make_item("TEMPLATE")
		frappe.db.set_value("Style Attribute Variant", {"route": self.route}, "item_style", template)
		self.send_token(self.token)

		with self.assertRaisesRegex(frappe.ValidationError, "is not for sale"):
			cart_sdk.add_lines([{"item_code": template, "qty": 1}])

	def test_a_zero_quantity_removes_the_line(self):
		line_id = add_lines([{"item_code": self.item_code, "qty": 1}])["lines"][0]["line_id"]

		cart = update_lines([{"line_id": line_id, "qty": 0}])

		self.assertEqual(cart["lines"], [])
		self.assertEqual(get_cart()["total_quantity"], 0)

	def get_checkout_code(self) -> str:
		return get_checkout_url()["path"].split("code=")[1]

	def test_a_checkout_code_moves_the_cart_to_a_new_browser_token_once(self):
		add_lines([{"item_code": self.item_code, "qty": 1}])
		code = self.get_checkout_code()
		self.send_token("unused-browser-token-0000000000000000")

		open_checkout(code)

		self.assertEqual(frappe.local.response["location"], f"/storefront-cart?code={code}")
		self.assertNotIn(GUEST_CART_COOKIE, frappe.local.cookie_manager.cookies)
		self.assertTrue(frappe.cache.get_value(f"{CHECKOUT_CODE_PREFIX}{code}"))
		claim_checkout_cart(code)

		browser_token = frappe.local.cookie_manager.cookies[GUEST_CART_COOKIE]["value"]
		self.assertNotIn(browser_token, (self.token, "unused-browser-token-0000000000000000"))
		self.assertEqual(frappe.local.response["location"], "/en/cart/checkout")
		self.assertTrue(
			frappe.db.exists("Commera Cart", {"cart_key": frappe.utils.sha256_hash(browser_token)})
		)
		claim_checkout_cart(code)
		self.assertEqual(frappe.local.response["location"], "/en/cart")

		self.send_token(self.token)
		self.assertIsNone(get_cart())

	def test_a_signed_in_browser_merges_the_storefront_cart_only_once_confirmed(self):
		add_lines([{"item_code": self.item_code, "qty": 3}])
		code = self.get_checkout_code()
		self.send_token(None, user=make_website_user())

		open_checkout(code)

		self.assertEqual(frappe.local.response["location"], f"/storefront-cart?code={code}")
		claim_checkout_cart(code)
		self.assertEqual(frappe.local.response["location"], f"/storefront-cart?code={code}")
		self.assertIsNone(get_session_cart())
		adopt_checkout_cart(code)
		self.assertEqual(
			[(row.item_code, row.qty) for row in get_session_cart().lines], [(self.item_code, 3)]
		)
		self.assertFalse(frappe.cache.get_value(f"{CHECKOUT_CODE_PREFIX}{code}"))

	def test_an_expired_checkout_code_opens_the_cart(self):
		add_lines([{"item_code": self.item_code, "qty": 1}])
		code = self.get_checkout_code()
		key = f"{CHECKOUT_CODE_PREFIX}{code}"
		frappe.cache.set_value(key, {**frappe.cache.get_value(key), "expires_at": 0}, expires_in_sec=60)
		self.send_token(None)

		open_checkout(code)

		self.assertEqual(frappe.local.response["location"], "/en/cart")
		self.assertNotIn(GUEST_CART_COOKIE, frappe.local.cookie_manager.cookies)

	def test_a_signed_in_checkout_code_leaves_time_to_sign_in_but_never_extends(self):
		self.send_token(None, user=make_website_user())
		add_lines([{"item_code": self.item_code, "qty": 1}])
		code = self.get_checkout_code()
		key = f"{CHECKOUT_CODE_PREFIX}{code}"
		expires_at = frappe.cache.get_value(key)["expires_at"]
		self.assertAlmostEqual(expires_at - time.time(), 15 * 60, delta=5)

		for _visit in range(2):
			self.send_token(None)
			open_checkout(code)

		self.assertEqual(frappe.cache.get_value(key)["expires_at"], expires_at)

	def test_lines_that_are_not_a_list_of_objects_are_refused(self):
		for lines in (None, "", "not json", '{"item_code": "x"}', "[1, 2]", ["x"]):
			with self.subTest(lines=lines):
				with self.assertRaisesRegex(frappe.ValidationError, "list of objects"):
					add_lines(lines)
				with self.assertRaisesRegex(frappe.ValidationError, "list of objects"):
					update_lines(lines)
		for line_ids in (None, "x", "[1]", [{"line_id": "x"}]):
			with self.subTest(line_ids=line_ids):
				with self.assertRaisesRegex(frappe.ValidationError, "list of strings"):
					remove_lines(line_ids)

	def test_checkout_needs_a_cart(self):
		with self.assertRaises(frappe.DoesNotExistError):
			get_checkout_url()

	def test_a_signed_in_shopper_adopts_the_guest_cart_of_the_token(self):
		add_lines([{"item_code": self.item_code, "qty": 2}])
		self.send_token(self.token, user=make_website_user())

		cart = adopt_cart()

		self.assertEqual([(line["item_code"], line["qty"]) for line in cart["lines"]], [(self.item_code, 2)])
		self.assertFalse(frappe.db.exists("Commera Cart", {"cart_key": frappe.utils.sha256_hash(self.token)}))

	def test_adopting_needs_the_cart_token(self):
		self.send_token(None, user="Administrator")

		with self.assertRaisesRegex(frappe.ValidationError, "cart token"):
			adopt_cart()

	def test_a_signed_in_checkout_code_opens_only_in_a_browser_of_the_same_shopper(self):
		shopper = make_website_user()
		self.send_token(None, user=shopper)
		add_lines([{"item_code": self.item_code, "qty": 1}])
		path = get_checkout_url()["path"]
		code = path.split("code=")[1]

		for browser_user in ("Guest", make_website_user()):
			with self.subTest(browser_user):
				self.send_token(None, user=browser_user, path=path)
				open_checkout(code)
				location = urlsplit(frappe.local.response["location"])
				self.assertEqual(location.path, "/storefront-login")
				self.assertEqual(parse_qs(location.query), {"prompt": ["login"], "redirect-to": [path]})

		self.send_token(None, user=shopper, path=path)
		open_checkout(code)
		self.assertEqual(frappe.local.response["location"], "/en/cart?checkout=1")
