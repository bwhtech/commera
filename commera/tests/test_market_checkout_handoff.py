from urllib.parse import parse_qsl, urlsplit

import frappe
from frappe.auth import CookieManager
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.server_cart import get_server_cart, sync_server_cart
from commera.api.storefront.cart import add_lines, claim_checkout_cart, get_checkout_url, open_checkout
from commera.commera_ecommerce.doctype.commera_cart.commera_cart import get_session_cart
from commera.guest import CART_TOKEN_HEADER, GUEST_CART_COOKIE
from commera.tests.test_market_cart import MarketCartTestCase

STOREFRONT_CART = "commera.api.storefront.cart"


class TestMarketCheckoutHandoff(MarketCartTestCase):
	"""A guest checks out a storefront cart. The Gulf market sells to AE; its items are not stock-tracked."""

	def setUp(self):
		super().setUp()
		# Every direct call shares one rate-limit counter for this IP, and it outlives the test.
		frappe.cache.delete_keys("rl:*127.0.0.1*")
		self.saved = (getattr(frappe.local, "request", None), frappe.local.form_dict, frappe.local.lang)
		self.addCleanup(self.restore_locals)
		self.token = frappe.generate_hash(length=32)
		self.item_code = self.item("HANDOFF", market_sale=300, market_compare_at=400)

	def restore_locals(self):
		frappe.local.request, frappe.local.form_dict, frappe.local.lang = self.saved

	def send(self, method, token=None, cookie=None, **form):
		headers = {CART_TOKEN_HEADER: token} if token else {}
		if cookie:
			headers["Cookie"] = f"{GUEST_CART_COOKIE}={cookie}"
		environ = EnvironBuilder(path=f"/api/v2/method/{method}", headers=headers).get_environ()
		frappe.local.request = Request(environ)
		frappe.local.request_ip = "127.0.0.1"
		frappe.local.cookie_manager = CookieManager()
		# set_user() clears form_dict, so the form comes after it.
		frappe.set_user("Guest")
		frappe.local.form_dict = frappe._dict(form)
		frappe.local.lang = "en"
		frappe.local.request_cache.clear()

	def start_checkout(self, qty=1, **form):
		self.send(f"{STOREFRONT_CART}.add_lines", token=self.token, **form)
		add_lines([{"item_code": self.item_code, "qty": qty}])
		return dict(parse_qsl(urlsplit(get_checkout_url()["path"]).query))

	def test_the_checkout_path_names_the_country_of_a_secondary_market(self):
		query = self.start_checkout(_country="AE")

		self.assertEqual((query["_lang"], query["_country"]), ("en", "AE"))

	def test_the_checkout_path_names_no_country_in_the_primary_market(self):
		query = self.start_checkout()

		self.assertNotIn("_country", query)

	def test_the_handoff_and_the_checkout_open_in_the_market(self):
		query = self.start_checkout(_country="AE")

		self.send(f"{STOREFRONT_CART}.open_checkout", **query)
		open_checkout(query["code"])
		handoff = urlsplit(frappe.local.response["location"])
		self.assertEqual(handoff.path, "/en-ae/storefront-cart")

		# The handoff page posts its query back as form fields.
		self.send(f"{STOREFRONT_CART}.claim_checkout_cart", **dict(parse_qsl(handoff.query)))
		claim_checkout_cart(query["code"])
		self.assertTrue(frappe.local.response["location"].startswith("/en-ae/cart"))

	def test_the_handoff_keeps_every_line(self):
		query = self.start_checkout(qty=2, _country="AE")
		self.send(f"{STOREFRONT_CART}.claim_checkout_cart", **query)
		claim_checkout_cart(query["code"])
		browser_token = frappe.local.cookie_manager.cookies[GUEST_CART_COOKIE]["value"]

		# The handoff page's cart script reads the cart, then may send the browser's empty list.
		self.send("commera.api.server_cart.get_server_cart", cookie=browser_token)
		shown = [(line["variant"]["item_code"], line["qty"]) for line in get_server_cart()["lines"]]
		self.assertEqual(shown, [(self.item_code, 2)])
		self.assertTrue(sync_server_cart([])["conflict"])

		self.assertEqual(
			[(row.item_code, row.qty) for row in get_session_cart().lines], [(self.item_code, 2)]
		)
