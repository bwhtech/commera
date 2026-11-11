"""Currency rules shared by storefront catalog, cart and order amounts."""

from dataclasses import dataclass

import frappe
from frappe.utils.data import flt, fmt_money

from commera.localization.formatter import (
	get_html_currency_symbol,
	get_money_precision,
	strip_fmt_money_symbol,
)
from commera.localization.market_prices import MarketPrices
from commera.utils import get_store_currency


@dataclass(frozen=True)
class CartCurrency:
	code: str
	symbol: str
	precision: int

	@classmethod
	def of(cls, quotation=None) -> "CartCurrency":
		code = (quotation and quotation.get("currency")) or MarketPrices.current().currency
		# Primary storefront templates have always printed two decimal places.
		precision = 2 if code == get_store_currency() else get_money_precision(code)
		return cls(code, get_html_currency_symbol(code), precision)

	@property
	def config(self) -> dict:
		return {"precision": self.precision}

	def amount(self, value: float | None) -> str:
		return f"{flt(value):.{self.precision}f}"

	def catalog_amount(self, value: float | None) -> str:
		# Summer product cards already use fmt_money, including its precision fallback.
		if self.code == get_store_currency():
			return fmt_money(flt(value), precision=2)
		return strip_fmt_money_symbol(
			fmt_money(flt(value), precision=self.precision, currency=self.code), self.code
		)


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
