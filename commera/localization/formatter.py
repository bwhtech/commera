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
from frappe.utils.number_format import NumberFormat

from commera.localization.date_formats import DATE_STYLES, DateFormats, get_babel_locale
from commera.localization.languages import Language
from commera.localization.resolver import get_localization
from commera.utils import (
	CURRENCY_SIGNS,
	get_currency_symbol,
	get_selling_currencies,
	get_store_currency,
	is_currency_symbol_hidden,
)

DEFAULT_NUMBER_FORMAT = "#,###.##"
NO_BREAK_SPACE = "\u00a0"


class Formatter:
	"""Money has the digits of ERPNext's print formats. A symbol goes after the amount in a right-to-left
	language or when its Currency's symbol_on_right is set, else before; a sign, always left."""

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
		formatted = format_money_digits(amount, precision, self.number_format, currency)
		symbol = get_html_currency_symbol(currency)
		if is_currency_sign(currency):
			formatted = formatted.replace("-", "\u2212", 1)
			return isolate_left_to_right(f"{symbol}{formatted}")
		return self.place_symbol(formatted, symbol, currency)

	def money_text(self, amount, currency=None, precision=None) -> str:
		currency = currency or get_store_currency()
		if precision is None:
			precision = get_money_precision(currency)
		formatted = format_money_digits(amount, precision, self.number_format, currency)
		symbol = get_currency_symbol(currency)
		if is_currency_sign(currency):
			formatted = formatted.replace("-", "\u2212", 1)
			return f"{symbol}{NO_BREAK_SPACE}{formatted}"
		return self.place_symbol(formatted, symbol, currency)

	def place_symbol(self, formatted: str, symbol: str, currency: str) -> str:
		if not symbol:
			return formatted
		sign, digits = split_sign(formatted)
		if self.language.direction == "rtl" or is_symbol_on_right(currency):
			return f"{sign}{digits}{NO_BREAK_SPACE}{symbol.strip()}"
		return f"{sign}{symbol}{digits}"

	def signed_money(self, amount, currency=None, minus="\u2212") -> str:
		"""Keep the literal minus used by themes for currencies without the new signs."""
		currency = currency or get_store_currency()
		if is_currency_sign(currency):
			return self.money(amount, currency)
		return (minus if amount < 0 else "") + self.money(abs(amount), currency)

	def number(self, value: float | None, precision: int = 0) -> str:
		return format_money_digits(value, precision, self.number_format)

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


def format_money_digits(value, precision: int, number_format: str, currency: str | None = None) -> str:
	amount = flt(value)
	if abs(amount) < 1e16:
		formatted = fmt_money(amount, precision=precision, currency=currency, format=number_format)
		return strip_fmt_money_symbol(formatted, currency) if currency else formatted

	# Frappe groups str(float(amount)), which uses scientific notation from 1e16 onward.
	format_info = NumberFormat.from_string(number_format)
	if format_info.decimal_separator and precision > 2:
		precision = get_fraction_precision(currency) if currency else format_info.precision
	whole, _, decimals = ("%.*f" % (precision, round(abs(amount), precision))).partition(".")
	groups = [whole[-3:]]
	whole = whole[:-3]
	size = 2 if number_format == "#,##,###.##" else 3
	while whole:
		groups.insert(0, whole[-size:])
		whole = whole[:-size]
	digits = format_info.thousands_separator.join(groups)
	if precision and format_info.decimal_separator:
		digits += format_info.decimal_separator + decimals
	return ("-" if amount < 0 else "") + digits


def get_money_format(currency: str) -> dict:
	"""The rules of the print path, format_value then fmt_money, for the JavaScript formatter."""
	return {
		"precision": get_money_precision(currency),
		"fraction_precision": get_fraction_precision(currency),
		"symbol_on_right": is_symbol_on_right(currency),
	}


def get_money_precision(currency: str) -> int:
	"""format_value's precision for a Currency field: the System Settings currency precision, else
	that of the currency's format (under "Use Number Format from Currency") or the system format."""
	return get_field_precision(frappe._dict(fieldtype="Currency"), currency=currency)


def get_fraction_precision(currency: str) -> int:
	"""fmt_money's fallback above 2 decimals when the amount has fewer: the currency's fraction units."""
	fraction_units = frappe.db.get_value("Currency", currency, "fraction_units", cache=True) or 100
	return len(cstr(fraction_units)) - 1


def is_symbol_on_right(currency: str) -> bool:
	"""The Currency's "Show Currency Symbol on Right Side", which fmt_money follows too."""
	return bool(frappe.db.get_value("Currency", currency, "symbol_on_right", cache=True))


def strip_fmt_money_symbol(formatted: str, currency: str) -> str:
	"""fmt_money adds the Currency record's symbol; Commera places its own by text direction."""
	if is_currency_symbol_hidden():
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


def email_money(amount: float | None, currency: str | None = None) -> str:
	"""fmt_money for order emails. Email clients ignore webfonts, so a riyal or dirham shows its code."""
	formatted = fmt_money(amount, currency=currency)
	if currency not in CURRENCY_SIGNS or is_currency_symbol_hidden():
		return formatted
	return f"{currency}{NO_BREAK_SPACE}{strip_fmt_money_symbol(formatted, currency)}"


def get_html_currency_symbol(currency: str) -> str:
	"""The escaped symbol to place before an amount. Screen readers may not know the new signs yet,
	so a sign reads as its currency code."""
	symbol = escape(get_currency_symbol(currency))
	if not is_currency_sign(currency):
		return symbol
	return f'<span class="currency-sign" role="img" aria-label="{escape(currency)}">{symbol}</span>{NO_BREAK_SPACE}'


def is_currency_sign(currency: str) -> bool:
	return get_currency_symbol(currency) in CURRENCY_SIGNS.values()


def isolate_left_to_right(html: str) -> str:
	# SAMA and the CBUAE put the sign left of the amount, and of a minus sign, on any page.
	return f'<bdi dir="ltr">{html}</bdi>'
