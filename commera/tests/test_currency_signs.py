import json
from html import escape
from pathlib import Path

import frappe
from frappe.utils.data import fmt_money

from commera.localization.formatter import Formatter, email_money, get_html_currency_symbol
from commera.localization.languages import Language
from commera.shop_themes.tests.test_theme_engine import STOREFRONT_CONFIG_PATTERN
from commera.tests.test_cart_currency import CartCurrencyTestCase
from commera.utils import get_currency_symbol

EMAIL_TEMPLATES = Path(frappe.get_app_path("commera", "fixtures", "email_template.json"))
SIGNS = (("SAR", "\u20c1"), ("AED", "\u20c3"))
OTHER_CURRENCIES = ("INR", "USD", "EUR")


class TestCurrencySigns(CartCurrencyTestCase):
	"""The Gulf market of CartCurrencyTestCase sells in AED."""

	def test_the_signs_are_plain_unicode_text(self):
		for currency, sign in SIGNS:
			with self.subTest(currency=currency):
				self.assertEqual(get_currency_symbol(currency), sign)
		# Unicode says U+FDFC RIAL SIGN must not be reused for the riyal.
		self.assertNotIn("\ufdfc", get_currency_symbol("SAR"))

	def test_the_page_config_carries_the_signs_without_html(self):
		html = self.render_summer("pages/cart/cart.html", "/en-ae/cart")
		symbols = json.loads(STOREFRONT_CONFIG_PATTERN.search(html).group(1))["currency_symbols"]
		self.assertEqual(symbols[self.currency], "\u20c3")
		self.assertFalse([symbol for symbol in symbols.values() if "<" in symbol])

	def test_rendered_pages_show_the_sign_as_escaped_text_with_its_code(self):
		label = '<span class="currency-sign" role="img" aria-label="AED">\u20c3</span>\u00a0'
		for theme, html in (
			("summer", self.render_summer("pages/cart/cart.html", "/en-ae/cart")),
			("legacy", self.render_legacy("cart/cart", "/en-ae/cart")),
		):
			with self.subTest(theme=theme):
				self.assertIn(f"{label}<span x-text=", html)
				self.assertNotIn("saudi-currency-symbol", html)

	def test_starter_money_isolates_the_sign_left_of_the_amount_in_both_directions(self):
		for code, direction in (("en", "ltr"), ("ar", "rtl")):
			formatter = Formatter(Language(code, code, code, direction), "#,###.##")
			for currency, sign in SIGNS:
				with self.subTest(language=code, currency=currency):
					self.assertEqual(
						formatter.money(-1234.5, currency, 2),
						f'<bdi dir="ltr"><span class="currency-sign" role="img" aria-label="{currency}">'
						f"{sign}</span>\u00a0-1,234.50</bdi>",
					)

	def test_other_currencies_keep_their_symbols(self):
		english = Formatter(Language("en", "English", "English", "ltr"), "#,###.##")
		for currency in OTHER_CURRENCIES:
			with self.subTest(currency=currency):
				symbol = frappe.db.get_value("Currency", currency, "symbol")
				self.assertEqual(get_currency_symbol(currency), symbol)
				self.assertEqual(get_html_currency_symbol(currency), escape(symbol))
				self.assertEqual(english.money(1234.5, currency, 2), f"{escape(symbol)}1,234.50")

	def test_order_emails_show_the_codes_of_the_signs(self):
		for currency, _ in SIGNS:
			with self.subTest(currency=currency):
				self.assertEqual(email_money(1234.5, currency), f"{currency}\u00a01,234.50")
				self.assertEqual(email_money(-1234.5, currency), f"{currency}\u00a0-1,234.50")
		for currency in OTHER_CURRENCIES:
			with self.subTest(currency=currency):
				self.assertEqual(email_money(1234.5, currency), fmt_money(1234.5, currency=currency))

	def test_the_order_email_templates_format_money_with_the_codes(self):
		templates = {template["name"]: template for template in json.loads(EMAIL_TEMPLATES.read_text())}
		for name in ("Order Confirmation", "Order Cancellation"):
			with self.subTest(template=name):
				source = templates[name]["response_html"]
				self.assertNotIn("fmt_money", source)
				html = frappe.render_template(source, self.email_context())
				self.assertIn("SAR\u00a01,234.50", html)
				self.assertNotIn("\u20c1", html)

	def email_context(self) -> dict:
		item = frappe._dict(item_name="Shirt", qty=1, amount=1234.5, custom_code_discount=0)
		return {
			"currency": "SAR",
			"customer_name": "Shopper",
			"company": "Store",
			"transaction_date": "2026-11-12",
			"items": [item],
			"taxes": [],
			"discount_rows": [],
			"payable_total": 1234.5,
			"order_link": "",
		}
