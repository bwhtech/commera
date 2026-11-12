"""Currency rules shared by storefront catalog, cart and order amounts."""

from dataclasses import dataclass

import frappe
from frappe.utils.data import flt, fmt_money

from commera.localization.formatter import (
	Formatter,
	get_fraction_precision,
	get_html_currency_symbol,
	get_money_precision,
	strip_fmt_money_symbol,
)
from commera.localization.market_prices import MarketPrices
from commera.utils import get_store_currency


@dataclass(frozen=True)
class CartCurrency:
	"""Digits as the localization formatter writes them, so every theme agrees with Starter.
	Templates place the symbol themselves: it goes before the amount."""

	code: str
	symbol: str
	precision: int
	fraction_precision: int
	number_format: str

	@classmethod
	def of(cls, quotation=None) -> "CartCurrency":
		code = (quotation and quotation.get("currency")) or MarketPrices.current().currency
		return cls(
			code,
			get_html_currency_symbol(code),
			get_money_precision(code),
			get_fraction_precision(code),
			Formatter.current().number_format,
		)

	@property
	def config(self) -> dict:
		"""The rules `commera.format.amount` needs to print the same digits in the browser."""
		return {
			"precision": self.precision,
			"fraction_precision": self.fraction_precision,
			"number_format": self.number_format,
		}

	def amount(self, value: float | None) -> str:
		formatted = fmt_money(
			flt(value), precision=self.precision, currency=self.code, format=self.number_format
		)
		return strip_fmt_money_symbol(formatted, self.code)


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
