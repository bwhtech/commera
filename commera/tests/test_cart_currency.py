import frappe
from frappe.auth import CookieManager
from frappe.website.page_renderers.template_page import TemplatePage
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.cart import get_detail_for_cart_items, update_variant
from commera.api.payments import generate_quotation_for_cart
from commera.api.server_cart import get_server_cart, sync_server_cart
from commera.commera_ecommerce.doctype.commera_cart.commera_cart import get_session_cart
from commera.guest import GUEST_CART_COOKIE
from commera.localization.cart_currency import CartCurrency
from commera.shop_themes.doctype.shop_theme.shop_theme import build_theme_context, render_theme_context
from commera.shop_themes.theme_resolver import ThemePageRenderer
from commera.tests.test_market_cart import MarketCartTestCase
from commera.utils import get_currency_symbol
from commera.www.cart.permalink import get_cart_lines

SUMMER = "Summer Theme"


class CartCurrencyTestCase(MarketCartTestCase):
	"""A Gulf cart of one item at 3499 in the market currency; the store sells it at 80."""

	def setUp(self):
		super().setUp()
		self.saved_request = getattr(frappe.local, "request", None)
		self.saved_form_dict = frappe.local.form_dict
		self.addCleanup(self.restore_request)
		self.set_default("currency_precision", "2")
		self.set_default("number_format", "#,###.##")
		self.item_code = self.item("CARTCURRENCY", market_sale=3499)
		self.market_symbol = get_currency_symbol(self.currency)
		self.store_symbol = get_currency_symbol(self.store_currency)
		self.sign_in_shopper()
		self.add(self.item_code)

	def set_default(self, key, value):
		previous = frappe.db.get_default(key)
		self.addCleanup(frappe.defaults.set_global_default, key, previous)
		frappe.defaults.set_global_default(key, value)

	def restore_request(self):
		frappe.local.request = self.saved_request
		frappe.local.form_dict = self.saved_form_dict

	def open_request(self, path):
		frappe.local.request = Request(EnvironBuilder(path=path).get_environ())
		frappe.local.form_dict = frappe._dict()
		frappe.local.request_cache.clear()

	def checkout_quotation(self, path):
		"""The cart's checkout quotation, priced in the market of `path` as the hand-off prices it."""
		self.open_request(path)
		return generate_quotation_for_cart({})

	def render_summer(self, template_path, path):
		self.open_request(path)
		with render_theme_context(build_theme_context(SUMMER)):
			renderer = ThemePageRenderer(path.strip("/"))
			renderer.theme_dirs = build_theme_context(SUMMER)["dirs"]
			renderer.template_path = template_path
			response = renderer.render()
		self.assertEqual(response.status_code, 200)
		return response.get_data(as_text=True)

	def render_legacy(self, route, path):
		self.open_request(path)
		with render_theme_context(build_theme_context(None)):
			response = TemplatePage(route).render()
		self.assertEqual(response.status_code, 200)
		return response.get_data(as_text=True)


class TestCartCurrency(CartCurrencyTestCase):
	def test_a_cart_without_a_quotation_is_in_the_market_currency(self):
		self.open_request("/en-ae/cart")
		self.assertEqual(CartCurrency.of(), CartCurrency(self.currency, self.market_symbol, 2))

		self.open_request("/cart")
		self.assertEqual(CartCurrency.of(), CartCurrency(self.store_currency, self.store_symbol, 2))

	def test_a_cart_with_a_quotation_is_in_the_quotation_currency(self):
		quotation = self.checkout_quotation("/en-ae/cart/checkout")

		self.open_request("/cart")
		self.assertEqual(CartCurrency.of(quotation).code, self.currency)
		self.assertEqual(CartCurrency.of(quotation).amount(3499), "3499.00")


class TestSummerCartCurrency(CartCurrencyTestCase):
	def test_the_market_checkout_shows_the_market_currency(self):
		self.checkout_quotation("/en-ae/cart/checkout")

		html = self.render_summer("pages/cart/checkout.html", "/en-ae/cart/checkout")

		self.assertIn(self.summary_subtotal(self.market_symbol, "3499.00"), html)
		self.assertIn(self.drawer_total(self.market_symbol), html)
		self.assertIn("commera.format.amount(", html)
		self.assertNotIn(f'<td class="price">{self.store_symbol}', html)

	def test_the_market_cart_page_and_drawer_show_the_market_currency(self):
		html = self.render_summer("pages/cart/cart.html", "/en-ae/cart")

		self.assertIn(self.cart_line_price(self.market_symbol), html)
		self.assertIn(self.drawer_total(self.market_symbol), html)
		self.assertNotIn(f'<td class="price">{self.store_symbol}', html)

	def test_the_primary_market_checkout_keeps_the_store_currency(self):
		self.checkout_quotation("/cart/checkout")

		html = self.render_summer("pages/cart/checkout.html", "/cart/checkout")

		self.assertIn(self.summary_subtotal(self.store_symbol, "80.00"), html)
		self.assertIn(self.drawer_total(self.store_symbol), html)
		self.assertNotIn(f'<td class="price">{self.market_symbol}', html)

	def test_the_primary_market_cart_page_keeps_the_store_currency(self):
		html = self.render_summer("pages/cart/cart.html", "/cart")

		self.assertIn(self.cart_line_price(self.store_symbol), html)
		self.assertIn(self.drawer_total(self.store_symbol), html)
		self.assertNotIn(f'<td class="price">{self.market_symbol}', html)

	def summary_subtotal(self, symbol, amount):
		return (
			f'<td class="price">{symbol}<span x-text="format_amount(active_summary.items_total'
			f' ?? active_summary.subtotal)">{amount}</span></td>'
		)

	def cart_line_price(self, symbol):
		return f'<strong>{symbol}<span x-text="format_amount($store.cart.price_of(cart_item))">'

	def drawer_total(self, symbol):
		return f'<h5 class="mb-0">{symbol}<span x-text="commera.format.amount($store.cart.total,'


class TestLegacyCartCurrency(CartCurrencyTestCase):
	def test_the_market_checkout_shows_the_market_currency(self):
		self.checkout_quotation("/en-ae/cart/checkout")

		html = self.render_legacy("cart/checkout", "/en-ae/cart/checkout")

		self.assertIn(f'{self.market_symbol} <span x-text="commera.format.amount(checkout_total,', html)
		self.assertNotIn(f"{self.store_symbol} <span", html)

	def test_the_market_cart_page_shows_the_market_currency(self):
		html = self.render_legacy("cart/cart", "/en-ae/cart")

		self.assertIn(f'{self.market_symbol}<span x-text="commera.format.amount($store.cart.total,', html)
		self.assertNotIn(f'{self.store_symbol}<span x-text="commera.format.amount($store.cart.total', html)

	def test_the_primary_market_pages_keep_the_store_currency(self):
		self.checkout_quotation("/cart/checkout")

		checkout = self.render_legacy("cart/checkout", "/cart/checkout")
		cart = self.render_legacy("cart/cart", "/cart")

		self.assertIn(f'{self.store_symbol} <span x-text="commera.format.amount(checkout_total,', checkout)
		self.assertIn(f'{self.store_symbol}<span x-text="commera.format.amount($store.cart.total,', cart)


class TestGuestCartMarket(CartCurrencyTestCase):
	def setUp(self):
		super().setUp()
		# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
		frappe.set_user("Administrator")
		self.route = self.make_market_variant("GUESTDRAWER", market_sale=1234.50, market_compare_at=1500)
		self.code = self.get_item_code(self.route)
		self.unpriced = self.item("GUESTUNPRICED")
		self.token = frappe.generate_hash(length=32)
		frappe.cache.delete_keys("rl:*127.0.0.1*")
		self.guest_request("AE")

	def guest_request(self, country=None):
		self.open_request("/api/v2/method/commera.api.server_cart.sync_server_cart")
		frappe.local.request = Request(
			EnvironBuilder(
				path="/api/v2/method/commera.api.server_cart.sync_server_cart",
				headers={"Cookie": f"{GUEST_CART_COOKIE}={self.token}"},
			).get_environ()
		)
		frappe.local.cookie_manager = CookieManager()
		frappe.local.request_ip = "127.0.0.1"
		# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
		frappe.set_user("Guest")
		frappe.local.form_dict = frappe._dict(_lang="en", _country=country)

	def detail(self, code):
		return get_detail_for_cart_items([{"variant": {"item_code": code}}])["stock_data"][code]

	def test_guest_drawer_refresh_uses_the_request_market(self):
		self.assertEqual(self.detail(self.code)["sale_price"], 1234.50)
		self.assertEqual(self.detail(self.code)["default_price"], 1500)
		self.assertIsNone(self.detail(self.unpriced)["sale_price"])
		self.assertEqual(self.detail(self.unpriced)["stock"], 0)
		self.guest_request()
		self.assertEqual(self.detail(self.code)["sale_price"], 80)
		self.assertEqual(self.detail(self.code)["default_price"], 100)

	def test_guest_size_change_uses_market_prices_and_refuses_unpriced_sizes(self):
		variant = frappe.db.get_value("Style Attribute Variant", {"route": self.route})
		self.assertEqual(update_variant(variant, "M")["price"], 1234.50)
		unpriced_variant = frappe.db.get_value("Color Size Item", {"item_code": self.unpriced}, "parent")
		with self.assertRaisesRegex(frappe.ValidationError, "not available in this market"):
			update_variant(unpriced_variant, "M")
		self.guest_request()
		self.assertEqual(update_variant(variant, "M")["price"], 80)

	def test_guest_sync_saves_market_and_reload_keeps_market_prices(self):
		sync_server_cart([{"item_code": self.code, "qty": 1}])
		self.assertEqual(get_session_cart().market, "gulf")
		self.guest_request("AE")
		self.assertEqual(get_server_cart()["lines"][0]["price"], 1234.50)
		self.assertEqual(self.detail(self.code)["sale_price"], 1234.50)
		self.guest_request()
		self.assertEqual(get_server_cart()["lines"][0]["price"], 80)
		sync_server_cart([{"item_code": self.code, "qty": 2}], get_session_cart().version)
		self.assertEqual(get_session_cart().market, "primary")

	def test_restoration_retains_unpriced_lines_through_quantity_sync(self):
		self.guest_request()
		sync_server_cart([{"item_code": self.code, "qty": 1}, {"item_code": self.unpriced, "qty": 1}])
		self.guest_request("AE")
		restored = get_server_cart()
		lines = {line["variant"]["item_code"]: line for line in restored["lines"]}
		self.assertEqual(set(lines), {self.code, self.unpriced})
		self.assertIsNone(lines[self.unpriced]["price"])
		self.assertFalse(lines[self.unpriced]["available"])
		sync_server_cart([{"item_code": code, "qty": 2} for code in lines], restored["version"])
		self.assertEqual(
			{line.item_code: line.qty for line in get_session_cart().lines},
			{
				self.code: 2,
				self.unpriced: 2,
			},
		)
		self.assertEqual(
			[line["variant"]["item_code"] for line in get_cart_lines({self.code: 1, self.unpriced: 1}, [])],
			[self.code],
		)
