"""Money, numbers and dates for one language. packages/storefront/formatter.js follows the same rules,
and packages/storefront/test/formatter-cases.json holds the cases both must pass."""

import datetime

import frappe
from babel.dates import format_date
from frappe import _
from frappe.locale import get_number_format
from frappe.utils.data import flt, fmt_money, get_currency_precision, getdate
from frappe.utils.number_format import NumberFormat

from commera.localization.date_formats import DATE_STYLES, DateFormats, get_babel_locale
from commera.localization.languages import Language
from commera.localization.resolver import get_localization
from commera.utils import get_currency_symbol, get_selling_currencies, get_store_currency

DEFAULT_NUMBER_FORMAT = "#,###.##"
NO_BREAK_SPACE = "\u00a0"


class Formatter:
	"""Money follows ERPNext's number format and precision, so a price reads as on the invoice.
	The symbol goes before the amount in a left-to-right language and after it in a right-to-left one."""

	def __init__(self, language: Language, number_format: str | None = None):
		self.language = language
		self.number_format = number_format or get_language_number_format(language.code)

	@classmethod
	def current(cls) -> "Formatter":
		return cls(get_localization().language)

	def money(self, amount: float | None, currency: str | None = None, precision: int | None = None) -> str:
		currency = currency or get_store_currency()
		money_format = get_money_format(currency, self.number_format)
		if precision is None:
			precision = money_format["precision"]
		formatted = fmt_money(flt(amount), precision=precision, format=money_format["number_format"])
		sign, digits = split_sign(formatted)
		symbol = get_currency_symbol(currency)
		if self.language.direction == "rtl":
			return f"{sign}{digits}{NO_BREAK_SPACE}{symbol.strip()}"
		return f"{sign}{symbol}{digits}"

	def number(self, value: float | None, precision: int = 0) -> str:
		return fmt_money(flt(value), precision=precision, format=self.number_format)

	def date(self, value: str | datetime.date | None, style: str = "medium") -> str:
		if not value:
			return ""
		if style not in DATE_STYLES:
			frappe.throw(_("Date style must be one of {0}.").format(", ".join(DATE_STYLES)))
		return format_date(getdate(value), style, locale=get_babel_locale(self.language.code))

	def as_config(self) -> dict:
		"""The resolved rules the JavaScript formatter needs: it reads no settings of its own."""
		return {
			"number_format": self.number_format,
			"money_formats": {
				currency: get_money_format(currency, self.number_format)
				for currency in get_selling_currencies()
			},
			"date_formats": DateFormats.for_language(self.language.code).as_dict(),
		}


def get_money_format(currency: str | None, language_format: str) -> dict:
	"""Frappe's rules: an explicit System Settings currency precision wins over the format's."""
	number_format = get_currency_number_format(currency) or language_format
	precision = get_currency_precision()
	if precision is None:
		precision = NumberFormat.from_string(number_format).precision
	return {"number_format": number_format, "precision": precision}


def get_currency_number_format(currency: str | None) -> str | None:
	"""A currency's own format applies only under "Use Number Format from Currency", as in Desk."""
	if not currency or not frappe.get_system_settings("use_number_format_from_currency"):
		return None
	return frappe.get_cached_value("Currency", currency, "number_format")


def split_sign(formatted: str) -> tuple[str, str]:
	return ("-", formatted[1:]) if formatted.startswith("-") else ("", formatted)


def get_language_number_format(code: str) -> str:
	try:
		return get_number_format(code).string
	except frappe.DoesNotExistError:
		return frappe.db.get_default("number_format") or DEFAULT_NUMBER_FORMAT
