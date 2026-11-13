import json
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.formatters import format_value
from frappe.utils.number_format import NumberFormat

import commera.sdk
from commera.localization import Localization
from commera.localization import formatter as formatter_module
from commera.localization.cart_currency import CartCurrency
from commera.localization.date_formats import DateFormats
from commera.localization.formatter import DEFAULT_NUMBER_FORMAT, Formatter
from commera.localization.languages import Language
from commera.utils import get_currency_symbol

# packages/storefront/test/formatter.test.js passes the same cases with the JavaScript formatter.
CASES_DIR = Path(__file__).resolve().parents[2] / "packages" / "storefront" / "test"


def load_cases(name: str):
	return json.loads((CASES_DIR / name).read_text())


class TestFormatterCases(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.cases = load_cases("formatter-cases.json")

	def setUp(self):
		symbols = self.cases["currency_symbols"]
		patcher = patch.object(formatter_module, "get_currency_symbol", lambda currency: symbols[currency])
		patcher.start()
		self.addCleanup(patcher.stop)

	def formatter_for(self, code: str, number_format: str | None = None) -> Formatter:
		language = self.cases["languages"][code]
		return Formatter(
			Language(code, code, code, language["direction"]), number_format or language["number_format"]
		)

	def test_money_per_language_and_currency(self):
		# fmt_money reads the fraction units from the Currency records, as in the cases.
		for case in self.cases["money"]:
			rules = self.cases["money_formats"][case["rules"]]
			with (
				self.subTest(**{key: case[key] for key in ("language", "rules", "currency", "amount")}),
				patch.object(formatter_module, "get_money_precision", lambda c, r=rules: r[c]["precision"]),
				patch.object(
					formatter_module, "is_symbol_on_right", lambda c, r=rules: r[c]["symbol_on_right"]
				),
			):
				formatter = self.formatter_for(case["language"])
				self.assertEqual(
					formatter.money(case["amount"], case["currency"], case["precision"]), case["expected"]
				)

	def test_number_per_language(self):
		for case in self.cases["number"]:
			with self.subTest(language=case["language"], value=case["value"]):
				formatter = self.formatter_for(case["language"], case.get("number_format"))
				self.assertEqual(formatter.number(case["value"], case["precision"]), case["expected"])

	def test_date_per_language_and_style(self):
		for case in self.cases["date"]:
			code = case["language"]
			with self.subTest(language=code, value=case["value"], style=case["style"]):
				formatter = Formatter(Language(code, code, code, "ltr"), DEFAULT_NUMBER_FORMAT)
				self.assertEqual(formatter.date(case["value"], case["style"]), case["expected"])

	def test_date_formats_match_babel(self):
		# The JavaScript formatter renders these; scripts/generate_date_cases.py rewrites them.
		for code, date_formats in self.cases["date_formats"].items():
			with self.subTest(language=code):
				self.assertEqual(DateFormats.for_language(code).as_dict(), date_formats)

	def test_number_matches_fmt_money_for_each_number_format(self):
		english = Language("en", "English", "English", "ltr")
		for number_format, amounts in load_cases("fmt-money-cases.json").items():
			formatter = Formatter(english, number_format)
			for amount, expected in amounts:
				with self.subTest(number_format=number_format, amount=amount):
					self.assertEqual(formatter.number(amount, 2), expected)

	def test_symbol_follows_the_text_direction(self):
		self.assertEqual(self.formatter_for("en").money(1234.5, "USD"), "$1,234.50")
		self.assertEqual(self.formatter_for("ar").money(1234.5, "USD"), "1,234.50\u00a0$")
		self.assertEqual(self.formatter_for("he").money(-5, "EUR"), "-5.00\u00a0€")


# The System Settings behind each set of rules in formatter-cases.json.
SETTINGS_FOR_RULES = {
	"currency_format_on": {"use_number_format_from_currency": 1, "currency_precision": ""},
	"currency_format_off": {"use_number_format_from_currency": 0, "currency_precision": ""},
	"currency_precision_4": {"use_number_format_from_currency": 1, "currency_precision": "4"},
}


class TestFormatterSources(IntegrationTestCase):
	def setUp(self):
		frappe.db.set_value("Currency", "INR", "number_format", "#,##,###.##")
		frappe.clear_document_cache("Currency", "INR")
		self.addCleanup(frappe.clear_document_cache, "Currency", "INR")
		self.symbol = get_currency_symbol("INR")
		self.formatter = Formatter(Language.from_code("en"), "#,###.##")

	def change_money_settings(self, **settings):
		return self.change_settings("System Settings", number_format="#,###.##", **settings)

	def test_money_matches_erpnext_print_formats(self):
		amounts = (1234567.891, 1234.5, 1.2, 1.2345, -0.5, 999999999.1234567)
		for rules, settings in SETTINGS_FOR_RULES.items():
			with self.subTest(rules=rules), self.change_money_settings(**settings):
				formatter = Formatter(Language.from_code(frappe.local.lang))
				for currency in ("INR", "JPY", "KWD", "USD"):
					for amount in amounts:
						self.assertEqual(
							formatter.money(amount, currency),
							print_format_money(amount, currency),
							f"{currency} {amount}",
						)

	def test_cases_rules_are_what_the_settings_resolve(self):
		cases = load_cases("formatter-cases.json")["money_formats"]
		for rules, settings in SETTINGS_FOR_RULES.items():
			with self.subTest(rules=rules), self.change_money_settings(**settings):
				resolved = {
					currency: formatter_module.get_money_format(currency) for currency in cases[rules]
				}
				self.assertEqual(resolved, cases[rules])

	def test_separators_follow_the_language_not_the_currency(self):
		with self.change_money_settings(use_number_format_from_currency=1, currency_precision=""):
			self.assertEqual(self.formatter.money(1234567, "INR"), f"{self.symbol}1,234,567.00")
			self.assertEqual(self.formatter.money(1234.5, "JPY"), f"{get_currency_symbol('JPY')}1,234")
			hindi = Formatter(Language.from_code("hi"), "#,##,###.##")
			self.assertEqual(hindi.money(1234567, "INR"), f"{self.symbol}12,34,567.00")
		with self.change_money_settings(use_number_format_from_currency=0, currency_precision=""):
			self.assertEqual(self.formatter.money(1234.5, "JPY"), f"{get_currency_symbol('JPY')}1,234.50")

	def test_a_short_fraction_takes_the_currency_fraction_units(self):
		with self.change_money_settings(use_number_format_from_currency=0, currency_precision="3"):
			self.assertEqual(self.formatter.money(1.2, "KWD"), f"{get_currency_symbol('KWD')}1.200")
			self.assertEqual(self.formatter.money(1.2, "USD"), f"{get_currency_symbol('USD')}1.20")

	def test_only_the_symbol_fmt_money_added_is_removed(self):
		# A symbol made of digits must not eat the amount's other end.
		for on_right, formatted, expected in ((0, "123 1 123", "1 123"), (1, "123 1 123", "123 1")):
			values = {"symbol": "123", "symbol_on_right": on_right}
			with (
				self.subTest(on_right=on_right),
				patch.object(
					frappe.db, "get_value", side_effect=lambda _dt, _dn, field, **_kw: values[field]
				),
			):
				self.assertEqual(formatter_module.strip_fmt_money_symbol(formatted, "XTS"), expected)

	def test_currency_precision_wins_over_the_number_format(self):
		with self.change_money_settings(use_number_format_from_currency=1, currency_precision="0"):
			self.assertEqual(self.formatter.money(1234567.4, "INR"), f"{self.symbol}1,234,567")
			self.assertEqual(
				formatter_module.get_money_format("INR"),
				{"precision": 0, "fraction_precision": 2, "symbol_on_right": False},
			)

	def test_config_sends_the_resolved_rules(self):
		with (
			self.change_money_settings(use_number_format_from_currency=1, currency_precision="3"),
			patch.object(formatter_module, "get_selling_currencies", return_value={"INR"}),
		):
			config = Formatter(Language.from_code("de"), "#.###,##").as_config()
		self.assertEqual(config["number_format"], "#.###,##")
		self.assertEqual(
			config["money_formats"],
			{"INR": {"precision": 3, "fraction_precision": 2, "symbol_on_right": False}},
		)
		self.assertEqual(config["date_formats"], DateFormats.for_language("de").as_dict())

	def test_language_number_format_comes_from_frappe(self):
		with patch.object(
			formatter_module, "get_number_format", return_value=NumberFormat.from_string("#.###,##")
		) as get_number_format:
			formatter = Formatter(Language.from_code("de"))
		get_number_format.assert_called_once_with("de")
		self.assertEqual(formatter.number(1234.5, 2), "1.234,50")

	def test_unknown_language_uses_the_system_number_format(self):
		formatter = Formatter(Language("zz", "zz", "zz", "ltr"))
		self.assertEqual(formatter.number_format, frappe.db.get_default("number_format") or "#,###.##")
		self.assertEqual(formatter.date("2026-03-05"), "Mar 5, 2026")

	def test_sdk_formats_in_the_current_language(self):
		arabic = Language.from_code("ar")
		localization = Localization(arabic, arabic, (arabic,), "")
		# The site's number format decides the grouping: pin it, as a site set up in India has lakhs.
		with (
			self.change_settings("System Settings", number_format="#,###.##"),
			patch.object(formatter_module, "get_localization", return_value=localization),
		):
			self.assertEqual(commera.sdk.format.money(1250, "USD"), "1,250.00\u00a0$")
			self.assertEqual(commera.sdk.format.number(1234567), "1,234,567")
			self.assertEqual(commera.sdk.format.date("2026-12-01"), "01\u200f/12\u200f/2026")
		self.assertEqual(commera.sdk.format.date(None), "")

	def test_unknown_date_style_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			Formatter(Language.from_code("en")).date("2026-03-05", "tiny")


def print_format_money(amount: float, currency: str) -> str:
	"""A Sales Invoice total as print formats show it, with Commera's symbol in place of the record's."""
	field = frappe.get_meta("Sales Invoice").get_field("grand_total")
	invoice = frappe._dict(doctype="Sales Invoice", name=f"print-{currency}", currency=currency)
	printed = format_value(amount, field, invoice)
	digits = printed.removeprefix(f"{frappe.db.get_value('Currency', currency, 'symbol')} ")
	sign, digits = ("-", digits[1:]) if digits.startswith("-") else ("", digits)
	return f"{sign}{get_currency_symbol(currency)}{digits}"


class TestCurrencySymbolSettings(IntegrationTestCase):
	"""The Currency's symbol_on_right and Global Defaults' hide_currency_symbol, which fmt_money follows."""

	def setUp(self):
		self.english = Formatter(Language.from_code("en"), "#,###.##")
		self.addCleanup(self.clear_caches)

	def clear_caches(self):
		frappe.db.value_cache.clear()
		frappe.clear_document_cache("Currency", "USD")
		frappe.clear_document_cache("Currency", "SAR")

	def put_symbol_on_the_right(self, currency):
		frappe.db.set_value("Currency", currency, "symbol_on_right", 1)
		self.addCleanup(frappe.db.set_value, "Currency", currency, "symbol_on_right", 0)
		self.clear_caches()

	def hide_symbols(self):
		before = frappe.defaults.get_global_default("hide_currency_symbol")
		frappe.db.set_default("hide_currency_symbol", "Yes")
		self.addCleanup(frappe.db.set_default, "hide_currency_symbol", before)

	def test_a_symbol_on_the_right_follows_the_amount(self):
		self.put_symbol_on_the_right("USD")

		self.assertEqual(self.english.money(-1234.5, "USD"), "-1,234.50\u00a0$")
		self.assertEqual(self.english.money_text(1234.5, "USD"), "1,234.50\u00a0$")
		self.assertTrue(formatter_module.get_money_format("USD")["symbol_on_right"])
		currency = CartCurrency.of({"currency": "USD"})
		self.assertEqual((currency.symbol, currency.symbol_after), ("", "\u00a0$"))

	def test_a_riyal_sign_stays_left_of_the_amount(self):
		self.put_symbol_on_the_right("SAR")

		self.assertTrue(self.english.money_text(1234.5, "SAR").startswith("\u20c1\u00a0"))
		currency = CartCurrency.of({"currency": "SAR"})
		self.assertEqual(currency.symbol_after, "")
		self.assertIn("\u20c1", currency.symbol)

	def test_hidden_symbols_leave_the_digits_only(self):
		self.hide_symbols()

		for code in ("en", "ar"):
			formatter = Formatter(Language.from_code(code), "#,###.##")
			for currency in ("USD", "SAR"):
				with self.subTest(language=code, currency=currency):
					self.assertEqual(formatter.money(1234.5, currency), "1,234.50")
					self.assertEqual(formatter.money_text(-1234.5, currency), "-1,234.50")
		currency = CartCurrency.of({"currency": "SAR"})
		self.assertEqual((currency.symbol, currency.symbol_after, currency.is_sign), ("", "", False))
		self.assertEqual(formatter_module.email_money(1234.5, "SAR"), "1,234.50")
