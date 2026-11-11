"""Money, numbers and dates for one language. packages/storefront/formatter.js follows the same rules,
and packages/storefront/test/formatter-cases.json holds the cases both must pass."""

import datetime
from html import escape

import frappe
from babel.dates import format_date
from frappe import _
from frappe.locale import get_number_format
from frappe.model.meta import get_field_precision
from frappe.utils.data import cstr, flt, fmt_money, getdate

from commera.localization.date_formats import DATE_STYLES, DateFormats, get_babel_locale
from commera.localization.languages import Language
from commera.localization.resolver import get_localization
from commera.utils import get_currency_symbol, get_selling_currencies, get_store_currency

DEFAULT_NUMBER_FORMAT = "#,###.##"
NO_BREAK_SPACE = "\u00a0"


class Formatter:
	"""Money has the digits of ERPNext's print formats, so a price reads as on the invoice.
	The symbol goes before the amount in a left-to-right language and after it in a right-to-left one."""

	def __init__(self, language: Language, number_format: str | None = None):
		self.language = language
		self.number_format = number_format or get_language_number_format(language.code)

	@classmethod
	def current(cls) -> "Formatter":
		return cls(get_localization().language)

	def money(self, amount: float | None, currency: str | None = None, precision: int | None = None) -> str:
		currency = currency or get_store_currency()
		if precision is None:
			precision = get_money_precision(currency)
		formatted = fmt_money(flt(amount), precision=precision, currency=currency, format=self.number_format)
		sign, digits = split_sign(strip_fmt_money_symbol(formatted, currency))
		symbol = get_html_currency_symbol(currency)
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
			"money_formats": {currency: get_money_format(currency) for currency in get_selling_currencies()},
			"date_formats": DateFormats.for_language(self.language.code).as_dict(),
		}


def get_money_format(currency: str) -> dict:
	"""The rules of the print path, format_value then fmt_money, for the JavaScript formatter."""
	return {
		"precision": get_money_precision(currency),
		"fraction_precision": get_fraction_precision(currency),
	}


def get_money_precision(currency: str) -> int:
	"""format_value's precision for a Currency field: the System Settings currency precision, else
	that of the currency's format (under "Use Number Format from Currency") or the system format."""
	return get_field_precision(frappe._dict(fieldtype="Currency"), currency=currency)


def get_fraction_precision(currency: str) -> int:
	"""fmt_money's fallback above 2 decimals when the amount has fewer: the currency's fraction units."""
	fraction_units = frappe.db.get_value("Currency", currency, "fraction_units", cache=True) or 100
	return len(cstr(fraction_units)) - 1


def strip_fmt_money_symbol(formatted: str, currency: str) -> str:
	"""fmt_money adds the Currency record's symbol; Commera places its own by text direction."""
	if frappe.defaults.get_global_default("hide_currency_symbol") in ("1", "Yes"):
		return formatted
	symbol = _(frappe.db.get_value("Currency", currency, "symbol", cache=True) or currency)
	# Only the side fmt_money used: a symbol made of digits could match the amount's other end.
	if frappe.db.get_value("Currency", currency, "symbol_on_right", cache=True):
		return formatted.removesuffix(f" {symbol}")
	return formatted.removeprefix(f"{symbol} ")


def split_sign(formatted: str) -> tuple[str, str]:
	return ("-", formatted[1:]) if formatted.startswith("-") else ("", formatted)


def get_language_number_format(code: str) -> str:
	try:
		return get_number_format(code).string
	except frappe.DoesNotExistError:
		return frappe.db.get_default("number_format") or DEFAULT_NUMBER_FORMAT


def get_html_currency_symbol(currency: str) -> str:
	symbol = get_currency_symbol(currency)
	return symbol if currency == "SAR" else escape(symbol)
