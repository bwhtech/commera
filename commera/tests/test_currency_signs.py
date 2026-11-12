import json
from html import escape
from pathlib import Path
from unittest.mock import patch

import frappe
import html5lib
from frappe.utils.data import fmt_money

from commera.localization.cart_currency import CartCurrency
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

	def test_arabic_cart_prices_share_one_ltr_isolate(self):
		self.checkout_quotation("/ar-ae/cart/checkout")
		for currency, _ in SIGNS:
			money = CartCurrency.of({"currency": currency})
			with patch.object(CartCurrency, "of", return_value=money):
				pages = (
					("summer", self.render_summer("pages/cart/cart.html", "/ar-ae/cart")),
					("legacy", self.render_legacy("cart/cart", "/ar-ae/cart")),
					(
						"summer checkout",
						self.render_summer("pages/cart/checkout.html", "/ar-ae/cart/checkout"),
					),
					("legacy checkout", self.render_legacy("cart/checkout", "/ar-ae/cart/checkout")),
				)
			for theme, html in pages:
				with self.subTest(theme=theme, currency=currency):
					tree = html5lib.parse(html, namespaceHTMLElements=False)
					self.assertEqual(tree.get("dir"), "rtl")
					parents = {child: parent for parent in tree.iter() for child in parent}
					signs = [node for node in tree.iter() if node.get("class") == "currency-sign"]
					self.assertTrue(signs)
					for sign in signs:
						pair = parents[sign]
						self.assertEqual((pair.tag, pair.get("dir")), ("bdi", "ltr"))
						self.assertEqual(sign.tail, "\u00a0")
						self.assertTrue(len(pair) > 1 or sign.tail.strip())
					if theme == "summer":
						for cell in tree.findall('.//td[@class="product-item-price"]'):
							self.assertFalse(list(cell.find("strong").iter("span")))

	def test_rendered_server_discounts_and_rounding_keep_the_currency_rules(self):
		self.open_request("/ar-ae/cart")
		for currency, sign in (*SIGNS, ("INR", "₹")):
			money = CartCurrency.of({"currency": currency})
			for template, marker, _ in (
				(
					"themes/summer_theme/pages/account/orders/detail.html",
					"amount(discount.amount)",
					"\u2212 ",
				),
				("templates/components/checkout_product_details.html", "amount(discount.amount)", "\u2212"),
				(
					"themes/summer_theme/pages/account/orders/detail.html",
					"amount(order.rounding_adjustment)",
					"",
				),
				(
					"templates/components/checkout_product_details.html",
					"amount(cart_quotation.rounding_adjustment)",
					"",
				),
			):
				with self.subTest(currency=currency, template=template, marker=marker):
					source = Path(frappe.get_app_path("commera", template)).read_text()
					lines = source.splitlines()
					index = next(i for i, line in enumerate(lines) if marker in line)
					line = lines[index]
					if "cart_quotation.rounding_adjustment" in marker:
						line = "\n".join(lines[index - 1 : index + 1])
					html = frappe.render_template(
						line,
						{
							"cart_currency": money,
							"get_cart_currency": lambda order: money,
							"order": frappe._dict(rounding_adjustment=-0.25),
							"cart_quotation": frappe._dict(rounding_adjustment=-0.25),
							"discount": frappe._dict(amount=10),
						},
					)
					tree = html5lib.parseFragment(html, namespaceHTMLElements=False)
					text = "".join(tree.itertext()).strip()
					amount = "-0.25" if "rounding" in marker else "-10.00"
					if currency in ("SAR", "AED"):
						pair = tree.find('.//bdi[@dir="ltr"]')
						self.assertIsNotNone(pair)
						self.assertEqual("".join(pair.itertext()), f"{sign}\u00a0{amount}")
					else:
						if "rounding" in marker:
							expected = "₹\n                -0.25" if "templates/" in template else "₹-0.25"
						else:
							expected = "\u2212₹ 10.00" if "templates/" in template else "\u2212 ₹10.00"
						self.assertEqual(text, expected)

	def test_sdk_money_is_plain_unicode_in_both_directions(self):
		for code, direction in (("en", "ltr"), ("ar", "rtl")):
			formatter = Formatter(Language(code, code, code, direction), "#,###.##")
			for currency, sign in SIGNS:
				for amount, expected in ((10, "10.00"), (-10, "-10.00"), (-0.25, "-0.25")):
					with self.subTest(language=code, currency=currency, amount=amount):
						self.assertEqual(formatter.money_text(amount, currency, 2), f"{sign}\u00a0{expected}")

	def test_starter_rendered_discounts_and_rounding_keep_the_minus_after_the_sign(self):
		import commera.sdk

		self.open_request("/ar-ae/account/orders")
		source = Path(
			frappe.get_app_path("commera", "themes/commera_starter/pages/account/orders/detail.html")
		).read_text()
		macro = source[
			source.index("{% macro summary_row") : source.index("{%- endmacro %}") + len("{%- endmacro %}")
		]
		for currency, sign in (*SIGNS, ("INR", "₹")):
			for amount, minus in ((10, "\u2212"), (0.25, "\u2212")):
				with self.subTest(currency=currency, amount=amount):
					html = frappe.render_template(
						macro + '{{ summary_row("Discount", amount, sign=minus) }}',
						{
							"commera": commera.sdk,
							"order": frappe._dict(currency=currency),
							"amount": amount,
							"minus": minus,
						},
					)
					tree = html5lib.parseFragment(html, namespaceHTMLElements=False)
					text = "".join(tree.find(".//dd").itertext())
					if currency == "INR":
						self.assertEqual(text, f"\u2212{amount:.2f}\u00a0₹")
					else:
						self.assertEqual(text, f"{sign}\u00a0-{amount:.2f}")
