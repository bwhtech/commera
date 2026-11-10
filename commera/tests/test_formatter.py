import json
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.number_format import NumberFormat

import commera.sdk
from commera.localization import Localization
from commera.localization import formatter as formatter_module
from commera.localization.formatter import Formatter
from commera.localization.languages import Language

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
		symbols, formats = self.cases["currency_symbols"], self.cases["currency_number_formats"]
		for name, value in (
			("get_currency_symbol", lambda currency: symbols[currency]),
			("get_currency_number_format", lambda currency: formats.get(currency)),
		):
			patcher = patch.object(formatter_module, name, value)
			patcher.start()
			self.addCleanup(patcher.stop)

	def formatter_for(self, code: str) -> Formatter:
		language = self.cases["languages"][code]
		return Formatter(Language(code, code, code, language["direction"]), language["number_format"])

	def test_money_per_language_and_currency(self):
		for case in self.cases["money"]:
			with self.subTest(**{key: case[key] for key in ("language", "currency", "amount")}):
				formatter = self.formatter_for(case["language"])
				self.assertEqual(
					formatter.money(case["amount"], case["currency"], case["precision"]), case["expected"]
				)

	def test_number_per_language(self):
		for case in self.cases["number"]:
			with self.subTest(language=case["language"], value=case["value"]):
				formatter = self.formatter_for(case["language"])
				self.assertEqual(formatter.number(case["value"], case["precision"]), case["expected"])

	def test_date_per_language_and_style(self):
		for case in self.cases["date"]:
			with self.subTest(language=case["language"], value=case["value"], style=case["style"]):
				formatter = self.formatter_for(case["language"])
				self.assertEqual(formatter.date(case["value"], case["style"]), case["expected"])

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


class TestFormatterSources(IntegrationTestCase):
	def test_currency_number_format_wins_over_the_language(self):
		frappe.db.set_value("Currency", "INR", "number_format", "#,##,###.##")
		frappe.clear_document_cache("Currency", "INR")
		self.addCleanup(frappe.clear_document_cache, "Currency", "INR")
		formatter = Formatter(Language.from_code("en"), "#,###.##")
		self.assertEqual(
			formatter.money(1234567, "INR"), f"{frappe.db.get_value('Currency', 'INR', 'symbol')}12,34,567.00"
		)
		self.assertEqual(formatter.number(1234567), "1,234,567")

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
		with patch.object(formatter_module, "get_localization", return_value=localization):
			self.assertEqual(commera.sdk.format.money(1250, "USD"), "1,250.00\u00a0$")
			self.assertEqual(commera.sdk.format.number(1234567), "1,234,567")
			self.assertEqual(commera.sdk.format.date("2026-12-01"), "01\u200f/12\u200f/2026")
		self.assertEqual(commera.sdk.format.date(None), "")

	def test_unknown_date_style_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			Formatter(Language.from_code("en")).date("2026-03-05", "tiny")
