from html import escape
from unittest.mock import patch

import frappe

from commera.localization.cart_currency import CartCurrency, get_cart_delivery_configuration
from commera.tests.test_cart_currency import CartCurrencyTestCase
from commera.www.cart.checkout import set_cart_context


class TestStorefrontCurrency(CartCurrencyTestCase):
	def test_grouping_and_decimal_separators(self):
		self.open_request("/en-ae/cart")
		for number_format, expected in (
			("#,##,###.##", "1,23,456.78"),
			("#.###,##", "123.456,78"),
		):
			self.set_default("number_format", number_format)
			self.assertEqual(CartCurrency.of().amount(123456.78), expected)

	def test_real_precision_three_and_primary_compatibility(self):
		self.set_default("currency_precision", "3")
		self.open_request("/en-ae/cart")
		currency = CartCurrency.of()
		self.assertEqual(currency.precision, 3)
		self.assertEqual(currency.amount(123.456), "123.456")
		self.assertEqual(currency.amount(123), "123.00")
		self.open_request("/cart")
		self.assertEqual(CartCurrency.of().precision, 2)
		self.assertEqual(CartCurrency.of().amount(123.456), "123.46")

	def test_three_decimal_currency_uses_its_real_fraction_units(self):
		self.set_default("currency_precision", "3")
		self.open_request("/en-ae/cart")
		currency = CartCurrency.of({"currency": "KWD"})
		self.assertEqual(currency.precision, 3)
		self.assertEqual(currency.amount(123.456), "123.456")
		self.assertEqual(currency.amount(123), "123.000")

	def test_only_the_hardcoded_sar_icon_is_trusted_html(self):
		symbol = '<b title="currency">&</b>'
		previous = frappe.db.get_value("Currency", self.currency, "symbol")
		self.addCleanup(self.restore_symbol, previous)
		frappe.db.set_value("Currency", self.currency, "symbol", symbol)
		frappe.clear_document_cache("Currency", self.currency)
		self.addCleanup(frappe.clear_document_cache, "Currency", self.currency)
		self.open_request("/en-ae/cart")
		self.assertEqual(CartCurrency.of().symbol, escape(symbol))
		self.assertEqual(
			CartCurrency.of({"currency": "SAR"}).symbol,
			'<span class="saudi-currency-symbol pe-0.5"></span>',
		)

	def restore_symbol(self, symbol):
		frappe.db.set_value("Currency", self.currency, "symbol", symbol)
		frappe.clear_document_cache("Currency", self.currency)

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
		self.assertEqual(html, f"{self.market_symbol}1,23,456.78<del>{self.market_symbol}1,30,000.00</del>")

	def test_order_item_macro_uses_order_currency_outside_its_market(self):
		self.open_request("/account/orders")
		html = frappe.render_template(
			'{% from "templates/macros/user_dashboard_product.html" import dashboard_product %}'
			'{{ dashboard_product("", "brand", "item", 1234.5, currency=currency) }}',
			{"currency": self.currency},
		)
		self.assertIn(f"{self.market_symbol} 1,234.50", html)
		self.assertNotIn(self.store_symbol, html)

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

	def test_primary_page_money_markup_matches_develop_bytes(self):
		self.open_request("/cart")
		self.set_default("currency_precision", "3")
		context = {
			"currency_symbol": self.store_symbol,
			"cart_currency": CartCurrency.of(),
			"checkout_summary": frappe._dict(items_total=123.456),
			"order": frappe._dict(currency=self.store_currency, payable_total=123.456),
		}
		cases = frappe.get_file_json(frappe.get_app_path("commera", "tests", "primary_currency_develop.json"))
		for case in cases:
			with self.subTest(page=case["template"]):
				source = frappe.get_jenv().loader.get_source(frappe.get_jenv(), case["template"])[0]
				if case["marker"] == "card_price":
					start = source.index("{% macro card_price(")
					after = source[start : source.index("{%- endmacro %}", start) + len("{%- endmacro %}")]
					call = "{{ card_price(123.456, 150.789, 10) }}"
				else:
					after = next(line.strip() for line in source.splitlines() if case["marker"] in line)
					call = ""
				before = frappe.render_template(case["before"] + call, context)
				self.assertEqual(frappe.render_template(after + call, context).encode(), before.encode())
