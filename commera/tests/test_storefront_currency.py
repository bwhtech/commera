from html import escape
from unittest.mock import patch

import frappe

import commera.sdk
from commera.api.checkout import apply_shipping_rule
from commera.localization.cart_currency import CartCurrency, get_cart_delivery_configuration
from commera.product_detail import get_product_detail
from commera.tests.test_cart_currency import CartCurrencyTestCase
from commera.www.cart.checkout import set_cart_context

# The market's AED draws a sign, so the hostile symbol goes on a currency that keeps its record's.
PLAIN_CURRENCY = "USD"


class TestStorefrontCurrency(CartCurrencyTestCase):
	def test_every_symbol_is_escaped_text(self):
		symbol = '<b title="currency">&</b>'
		self.set_symbol(symbol)
		self.open_request("/en-ae/cart")
		self.assertEqual(CartCurrency.of({"currency": PLAIN_CURRENCY}).symbol, escape(symbol))
		for currency, sign in (("SAR", "\u20c1"), ("AED", "\u20c3")):
			with self.subTest(currency=currency):
				self.assertEqual(
					CartCurrency.of({"currency": currency}).symbol,
					f'<span class="currency-sign" role="img" aria-label="{currency}">{sign}</span>\u00a0',
				)

	def test_starter_money_escapes_symbols_and_labels_the_signs(self):
		self.open_request("/en-ae/products")
		symbol = '<img src=x onerror=alert(1)> & "currency"'
		self.set_symbol(symbol)
		for currency, expected in (
			(PLAIN_CURRENCY, escape(symbol)),
			("SAR", '<span class="currency-sign" role="img" aria-label="SAR">\u20c1</span>\u00a0'),
		):
			with self.subTest(currency=currency):
				html = frappe.render_template(
					'{% from "themes/commera_starter/components/macros/price.html" import price with context %}'
					"{{ price(product) }}",
					{
						"product": frappe._dict(price=10, compare_at_price=20, currency=currency),
						"commera": commera.sdk,
					},
				)
				self.assertEqual(html.count(expected), 2)
				self.assertNotIn("<img", html)

	def set_symbol(self, symbol):
		self.addCleanup(self.restore_symbol, frappe.db.get_value("Currency", PLAIN_CURRENCY, "symbol"))
		frappe.db.set_value("Currency", PLAIN_CURRENCY, "symbol", symbol)
		frappe.clear_document_cache("Currency", PLAIN_CURRENCY)

	def restore_symbol(self, symbol):
		frappe.db.set_value("Currency", PLAIN_CURRENCY, "symbol", symbol)
		frappe.clear_document_cache("Currency", PLAIN_CURRENCY)

	def test_shipping_amount_and_threshold_are_in_cart_currency(self):
		self.open_request("/en-ae/cart")
		with (
			patch("commera.utils.get_delivery_configuration", return_value=(100, 1000)),
			patch("erpnext.setup.utils.get_exchange_rate", return_value=20),
		):
			self.assertEqual(get_cart_delivery_configuration(), (5, 50))
			self.assertEqual(
				get_cart_delivery_configuration({"currency": self.currency, "conversion_rate": 25}),
				(4, 40),
			)
			self.assertEqual(get_cart_delivery_configuration({"currency": self.store_currency}), (100, 1000))

	def test_stale_quotation_omits_request_market_compare_at_prices(self):
		quotation = self.checkout_quotation("/en-ae/cart/checkout")
		self.open_request("/cart/checkout")
		context = frappe._dict()
		with (
			patch("commera.www.cart.checkout._get_cart_quotation", return_value=quotation),
			patch(
				"commera.www.cart.checkout.get_checkout_items",
				return_value=[frappe._dict(item_code=self.item_code)],
			),
		):
			set_cart_context(context, frappe.get_cached_doc("Commera Settings"))
			with patch("commera.www.cart.checkout.get_session_cart", return_value=None):
				without_cart = frappe._dict()
				set_cart_context(without_cart, frappe.get_cached_doc("Commera Settings"))
				self.assertTrue(all(not item.get("default_price") for item in without_cart["items"]))
		self.assertTrue(context.cart_needs_refresh)
		self.assertTrue(context["items"])
		self.assertTrue(all(not item.get("default_price") for item in context["items"]))
		self.assertEqual(CartCurrency.of(context.cart_quotation).code, self.currency)
		html = self.render_legacy("cart/checkout", "/cart/checkout")
		self.assertIn(self.market_symbol, html)
		self.assertNotIn(f'{self.store_symbol} <span x-text="commera.format.amount(checkout_total,', html)

	def test_catalog_sale_and_compare_at_use_request_market(self):
		self.open_request("/en-ae/products")
		self.set_default("number_format", "#,##,###.##")
		html = frappe.render_template(
			'{% from "themes/summer_theme/components/macros/product_card.html" import card_price %}'
			"{{ card_price(123456.78, 130000, 5) }}",
			{},
		)
		self.assertEqual(html, f"{self.priced('1,23,456.78')}<del>{self.priced('1,30,000.00')}</del>")

	def test_order_item_macro_uses_order_currency_outside_its_market(self):
		self.open_request("/account/orders")
		html = frappe.render_template(
			'{% from "templates/macros/user_dashboard_product.html" import dashboard_product %}'
			'{{ dashboard_product("", "brand", "item", 1234.5, currency=currency) }}',
			{"currency": self.currency},
		)
		self.assertIn(self.priced("1,234.50"), html)
		self.assertNotIn(self.store_symbol, html)

	def priced(self, amount):
		# The signs (SAR, AED) come wrapped in an ltr bdi; other symbols are plain.
		text = f"{self.market_symbol}{amount}"
		return f'<bdi dir="ltr">{text}</bdi>' if "currency-sign" in text else text

	def test_order_page_totals_use_order_currency_outside_its_market(self):
		self.open_request("/account/orders")
		order = frappe._dict(currency=self.currency, payable_total=1234.5)
		for template in (
			"themes/summer_theme/pages/account/dashboard.html",
			"themes/summer_theme/pages/account/orders/index.html",
			"themes/summer_theme/pages/account/orders/confirmation.html",
			"themes/summer_theme/pages/account/orders/detail.html",
		):
			with self.subTest(template=template):
				source = frappe.get_jenv().loader.get_source(frappe.get_jenv(), template)[0]
				line = next(line for line in source.splitlines() if "amount(order.payable_total)" in line)
				html = frappe.render_template(line, {"order": order})
				self.assertIn(f"{self.market_symbol}1,234.50", html)
				self.assertNotIn(self.store_symbol, html)

	def test_wishlist_and_search_use_market_formatter_in_both_themes(self):
		wishlist = self.render_summer("pages/account/wishlist.html", "/en-ae/account/wishlist")
		self.assertIn(self.market_symbol, wishlist)
		self.assertIn("commera.format.amount(", wishlist)
		self.open_request("/en-ae/products")
		html = frappe.render_template(
			'{% from "templates/macros/search_bar_modal.html" import search_bar %}{{ search_bar() }}',
			{},
		)
		self.assertIn(self.market_symbol, html)
		self.assertIn("commera.format.amount(", html)

	def test_price_filter_labels_keep_whole_numbers(self):
		# The range labels show rounded amounts in the page's number format; the symbol follows the market.
		sidebar = frappe.get_app_path(
			"commera", "themes", "summer_theme", "components", "sections", "shop_filter_sidebar.html"
		)
		with open(sidebar) as source:  # nosemgrep
			text = source.read()
		self.assertIn('x-text="commera.format.number(Math.round(minimum))"', text)
		self.assertIn('x-text="commera.format.number(Math.round(maximum))"', text)
		self.assertIn("get_cart_currency().symbol", text)


class TestProductPageCurrency(CartCurrencyTestCase):
	def setUp(self):
		super().setUp()
		self.shopper = frappe.session.user
		# The cart fixture signs in a shopper; product fixtures need catalog write access.
		# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
		frappe.set_user("Administrator")
		frappe.local.request_ip = "127.0.0.1"

	def open_request(self, path):
		super().open_request(path)
		if "/products/" in path:
			frappe.local.form_dict.route = path.rsplit("/", 1)[-1]

	def test_both_product_pages_use_market_prices_throughout(self):
		route = self.make_market_variant("PAGECURRENCY", market_sale=1234.5, market_compare_at=1500)
		for summer in (True, False):
			with self.subTest(summer=summer):
				path = f"/en-ae/products/{route}"
				html = (
					self.render_summer("pages/products/details.html", path)
					if summer
					else self.render_legacy("products/details", path)
				)
				self.assertIn(self.market_symbol, html)
				self.assertIn("1,234.50", html)
				self.assertIn('content="1234.50"', html)
				self.assertIn('"priceCurrency": "' + self.currency + '"', html)
				self.assertIn("price: 1234.5," if summer else "price:`1234.5`", html)
				self.assertIn("default_price: 1500.0," if summer else "default_price:`1500.0`", html)

	def test_compare_at_only_and_free_market_prices(self):
		full = self.make_market_variant("PAGEFULL", market_compare_at=400)
		free = self.make_market_variant("PAGEFREE", market_sale=0, market_compare_at=400)
		for route, expected, compare_at in ((full, 400, None), (free, 0, 400)):
			self.open_request(f"/en-ae/products/{route}")
			detail = get_product_detail(route)
			self.assertEqual(detail["selected_price"], expected)
			self.assertEqual(detail["default_price"], compare_at)
			self.assertTrue(detail["in_stock"])

	def test_unpriced_sizes_are_unavailable_and_have_no_store_price(self):
		route = self.make_market_variant("PAGEUNPRICED")
		self.open_request(f"/en-ae/products/{route}")
		detail = get_product_detail(route)
		self.assertIsNone(detail["selected_price"])
		self.assertIsNone(detail["default_price"])
		self.assertFalse(detail["in_stock"])
		self.assertFalse(detail["available_sizes"][0]["stock_detail"]["in_stock"])

	def test_shipping_api_returns_quotation_currency_amounts(self):
		# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
		frappe.set_user(self.shopper)
		quotation = self.checkout_quotation("/en-ae/cart/checkout")
		quotation.db_set("conversion_rate", 25)
		with (
			patch("commera.api.checkout._get_cart_quotation", return_value=quotation),
			patch("commera.api.checkout.get_open_gateway_payment_request", return_value="paying"),
			patch("commera.utils.get_delivery_configuration", return_value=(500, 5000)),
		):
			self.assertEqual(apply_shipping_rule(), (20, 200))
