"""Currency rules shared by storefront catalog, cart and order amounts."""

from dataclasses import dataclass

import frappe
from frappe.utils.data import flt

from commera.localization.formatter import (
	NO_BREAK_SPACE,
	Formatter,
	format_money_digits,
	get_fraction_precision,
	get_html_currency_symbol,
	get_money_precision,
	is_currency_sign,
	is_symbol_on_right,
)
from commera.localization.market_prices import MarketPrices
from commera.utils import get_store_currency


@dataclass(frozen=True)
class CartCurrency:
	"""Digits as the localization formatter writes them. Templates print `symbol` before the digits and
	`symbol_after` after them: the Currency's symbol_on_right moves it after, as in fmt_money."""

	code: str
	symbol: str
	precision: int
	fraction_precision: int
	number_format: str
	symbol_after: str = ""

	@classmethod
	def of(cls, quotation=None) -> "CartCurrency":
		code = (quotation and quotation.get("currency")) or MarketPrices.current().currency
		symbol = get_html_currency_symbol(code)
		# A riyal or dirham sign stays left of the amount.
		if symbol and not is_currency_sign(code) and is_symbol_on_right(code):
			symbol, symbol_after = "", NO_BREAK_SPACE + symbol.strip()
		else:
			symbol_after = ""
		return cls(
			code,
			symbol,
			get_money_precision(code),
			get_fraction_precision(code),
			Formatter.current().number_format,
			symbol_after,
		)

	@property
	def is_sign(self) -> bool:
		return is_currency_sign(self.code)

	@property
	def config(self) -> dict:
		"""The rules `commera.format.amount` needs to print the same digits in the browser."""
		return {
			"precision": self.precision,
			"fraction_precision": self.fraction_precision,
			"number_format": self.number_format,
			"is_sign": self.is_sign,
		}

	def amount(self, value: float | None) -> str:
		formatted = format_money_digits(value, self.precision, self.number_format, self.code)
		return formatted.replace("-", "\u2212", 1) if self.is_sign else formatted


def get_cart_currency(quotation=None) -> CartCurrency:
	return CartCurrency.of(quotation)


def get_cart_delivery_configuration(quotation=None) -> tuple[float, float]:
	from erpnext.setup.utils import get_exchange_rate

	from commera.utils import get_delivery_configuration

	charge, threshold = get_delivery_configuration()
	currency = CartCurrency.of(quotation).code
	if currency == get_store_currency() or not (charge or threshold):
		return charge, threshold
	conversion = (quotation and quotation.get("conversion_rate")) or get_exchange_rate(
		currency, get_store_currency()
	)
	if not conversion:
		frappe.throw(frappe._("No exchange rate found for delivery charges."))
	# Shipping Rule bands and amounts are in company currency, as in shipping.pricing.get_rule_amount.
	return flt(flt(charge) / conversion, 2), flt(flt(threshold) / conversion, 2)
