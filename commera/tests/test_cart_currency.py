from unittest.mock import patch

import frappe
from frappe.website.page_renderers.template_page import TemplatePage
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.api.payments import generate_quotation_for_cart
from commera.localization import cart_currency as cart_currency_module
from commera.localization.cart_currency import CartCurrency
from commera.shop_themes.doctype.shop_theme.shop_theme import build_theme_context, render_theme_context
from commera.shop_themes.theme_resolver import ThemePageRenderer
from commera.tests.test_market_cart import MarketCartTestCase
from commera.utils import get_currency_symbol

SUMMER = "Summer Theme"


class CartCurrencyTestCase(MarketCartTestCase):
	"""A Gulf cart of one item at 3499 in the market currency; the store sells it at 80."""

	def setUp(self):
		super().setUp()
		self.saved_request = getattr(frappe.local, "request", None)
		self.saved_form_dict = frappe.local.form_dict
		self.addCleanup(self.restore_request)
		# The amounts print with toFixed and "%.2f"; pin the precision that both pages had.
		patcher = patch.object(cart_currency_module, "get_money_precision", lambda currency: 2)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.item_code = self.item("CARTCURRENCY", market_sale=3499)
		self.market_symbol = get_currency_symbol(self.currency)
		self.store_symbol = get_currency_symbol(self.store_currency)
		self.sign_in_shopper()
		self.add(self.item_code)

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
		self.assertIn("toFixed(2)", html)
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
		return f'<h5 class="mb-0">{symbol}<span x-text="$store.cart.total.toFixed(2)"></span></h5>'


class TestLegacyCartCurrency(CartCurrencyTestCase):
	def test_the_market_checkout_shows_the_market_currency(self):
		self.checkout_quotation("/en-ae/cart/checkout")

		html = self.render_legacy("cart/checkout", "/en-ae/cart/checkout")

		self.assertIn(f'{self.market_symbol} <span x-text="checkout_total.toFixed(2)"', html)
		self.assertNotIn(f"{self.store_symbol} <span", html)

	def test_the_market_cart_page_shows_the_market_currency(self):
		html = self.render_legacy("cart/cart", "/en-ae/cart")

		self.assertIn(f'{self.market_symbol}<span x-text="$store.cart.total.toFixed(2)"', html)
		self.assertNotIn(f'{self.store_symbol}<span x-text="$store.cart.total', html)

	def test_the_primary_market_pages_keep_the_store_currency(self):
		self.checkout_quotation("/cart/checkout")

		checkout = self.render_legacy("cart/checkout", "/cart/checkout")
		cart = self.render_legacy("cart/cart", "/cart")

		self.assertIn(f'{self.store_symbol} <span x-text="checkout_total.toFixed(2)"', checkout)
		self.assertIn(f'{self.store_symbol}<span x-text="$store.cart.total.toFixed(2)"', cart)
