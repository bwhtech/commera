"""Money, numbers and dates for one language. packages/storefront/formatter.js follows the same rules,
and packages/storefront/test/formatter-cases.json holds the cases both must pass."""

import datetime

import frappe
from babel import Locale, UnknownLocaleError
from babel.dates import format_date
from frappe import _
from frappe.locale import get_number_format
from frappe.utils.data import flt, fmt_money, getdate
from frappe.utils.number_format import NumberFormat

from commera.localization.languages import FALLBACK_LANGUAGE, Language
from commera.localization.resolver import get_localization
from commera.utils import get_currency_symbol, get_store_currency

DEFAULT_NUMBER_FORMAT = "#,###.##"
DATE_STYLES = ("short", "medium", "long", "full")
NO_BREAK_SPACE = "\u00a0"


class Formatter:
	"""Money uses its currency's Frappe number format, else the language's, as Desk does.
	The symbol goes before the amount in a left-to-right language and after it in a right-to-left one."""

	def __init__(self, language: Language, number_format: str | None = None):
		self.language = language
		self.number_format = number_format or get_language_number_format(language.code)

	@classmethod
	def current(cls) -> "Formatter":
		return cls(get_localization().language)

	def money(self, amount: float | None, currency: str | None = None, precision: int | None = None) -> str:
		currency = currency or get_store_currency()
		number_format = get_currency_number_format(currency) or self.number_format
		if precision is None:
			precision = NumberFormat.from_string(number_format).precision
		sign, digits = split_sign(fmt_money(flt(amount), precision=precision, format=number_format))
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


def split_sign(formatted: str) -> tuple[str, str]:
	return ("-", formatted[1:]) if formatted.startswith("-") else ("", formatted)


def get_currency_number_format(currency: str | None) -> str | None:
	return frappe.get_cached_value("Currency", currency, "number_format") if currency else None


def get_language_number_format(code: str) -> str:
	try:
		return get_number_format(code).string
	except frappe.DoesNotExistError:
		return frappe.db.get_default("number_format") or DEFAULT_NUMBER_FORMAT


def get_babel_locale(code: str) -> Locale:
	try:
		return Locale.parse(code, sep="-")
	except (UnknownLocaleError, ValueError):
		return Locale.parse(FALLBACK_LANGUAGE)
