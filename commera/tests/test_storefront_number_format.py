import json
from pathlib import Path

import frappe

from commera.localization.cart_currency import CartCurrency
from commera.localization.formatter import Formatter, get_html_currency_symbol
from commera.localization.languages import Language
from commera.tests.test_cart_currency import CartCurrencyTestCase

# packages/storefront/test/format.test.js passes the same cases with commera.format.amount.
AMOUNT_CASES = Path(__file__).resolve().parents[2] / "packages" / "storefront" / "test" / "amount-cases.json"
INDIAN = "#,##,###.##"


class TestStorefrontNumberFormat(CartCurrencyTestCase):
	def setUp(self):
		super().setUp()
		self.set_default("number_format", INDIAN)

	def test_amounts_match_the_javascript_cases(self):
		for case in json.loads(AMOUNT_CASES.read_text()):
			with self.subTest(**{key: case[key] for key in ("number_format", "currency", "amount")}):
				currency = CartCurrency(
					case["currency"], "", case["precision"], case["fraction_precision"], case["number_format"]
				)
				self.assertEqual(currency.amount(case["amount"]), case["expected"])
				starter = Formatter(Language("en", "English", "English", "ltr"), case["number_format"])
				sign = "-" if case["expected"].startswith("-") else ""
				digits = case["expected"].removeprefix("-")
				self.assertEqual(
					starter.money(case["amount"], case["currency"], case["precision"]),
					f"{sign}{get_html_currency_symbol(case['currency'])}{digits}",
				)

	def test_amounts_and_browser_rules_follow_the_store_number_format(self):
		for path in ("/cart", "/en-ae/cart"):
			for number_format, expected in ((INDIAN, "1,23,456.78"), ("#.###,##", "123.456,78")):
				with self.subTest(path=path, number_format=number_format):
					self.set_default("number_format", number_format)
					self.open_request(path)
					currency = CartCurrency.of()
					self.assertEqual(currency.amount(123456.78), expected)
					self.assertEqual(currency.amount(-123456.78), f"-{expected}")
					self.assertEqual(currency.amount(None), "0.00" if number_format == INDIAN else "0,00")
					self.assertEqual(
						currency.config,
						{"precision": 2, "fraction_precision": 2, "number_format": number_format},
					)

	def test_precision_three_applies_to_store_and_market_currencies(self):
		self.set_default("currency_precision", "3")
		for path in ("/cart", "/en-ae/cart"):
			with self.subTest(path=path):
				self.open_request(path)
				currency = CartCurrency.of()
				self.assertEqual(currency.precision, 3)
				self.assertEqual(currency.amount(123456.789), "1,23,456.789")
				# A whole amount drops to the currency's fraction units, as on ERPNext print formats.
				self.assertEqual(currency.amount(123), "123.00")
		kuwaiti = CartCurrency.of({"currency": "KWD"})
		self.assertEqual(kuwaiti.amount(123), "123.000")

	def test_cart_amounts_print_the_starter_digits(self):
		for path in ("/cart", "/en-ae/cart"):
			with self.subTest(path=path):
				self.open_request(path)
				currency = CartCurrency.of()
				starter = Formatter.current().money(123456.78, currency.code)
				self.assertEqual(starter, f"{currency.symbol}{currency.amount(123456.78)}")

	def test_primary_and_market_pages_render_grouped_amounts(self):
		for path, symbol in (("/cart", self.store_symbol), ("/en-ae/cart", self.market_symbol)):
			with self.subTest(path=path):
				self.open_request(path)
				context = {
					"cart_currency": CartCurrency.of(),
					"currency_symbol": symbol,
					"checkout_summary": frappe._dict(items_total=123456.78),
				}
				summer = self.render_line(
					"themes/summer_theme/pages/cart/checkout.html", "format_amount(active_summary", context
				)
				self.assertIn(f"{symbol}<span", summer)
				self.assertIn(">1,23,456.78</span>", summer)
				legacy = self.render_line(
					"templates/components/checkout_product_details.html",
					"charge_summary.items_total",
					context,
				)
				self.assertIn(">1,23,456.78</span>", legacy)
				# The browser re-renders this span with the same rules.
				self.assertIn("commera.format.amount(charge_summary.items_total", legacy)
				self.assertIn(INDIAN, legacy)
				card = frappe.render_template(
					'{% from "themes/summer_theme/components/macros/product_card.html" import card_price %}'
					"{{ card_price(123456.78, 150000, 10) }}",
					{},
				)
				self.assertEqual(card, f"{symbol}1,23,456.78<del>{symbol}1,50,000.00</del>")

	def test_historical_orders_render_grouped_amounts_in_their_currency(self):
		self.open_request("/account/orders")
		order = frappe._dict(currency=self.currency, payable_total=123456.78)
		for template in (
			"themes/summer_theme/pages/account/orders/confirmation.html",
			"themes/summer_theme/pages/account/orders/index.html",
		):
			with self.subTest(template=template):
				html = self.render_line(template, "amount(order.payable_total)", {"order": order})
				self.assertIn(f"{self.market_symbol}1,23,456.78", html)
		legacy = frappe.render_template(
			'{% from "templates/macros/user_dashboard_product.html" import dashboard_product %}'
			'{{ dashboard_product("", "brand", "item", 123456.78, currency=currency) }}',
			{"currency": self.currency},
		)
		self.assertIn(f"{self.market_symbol} 1,23,456.78", legacy)

	def render_line(self, template, marker, context):
		source = frappe.get_jenv().loader.get_source(frappe.get_jenv(), template)[0]
		line = next(line for line in source.splitlines() if marker in line)
		return frappe.render_template(line, context)
