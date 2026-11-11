"""The currency a cart shows its amounts in. The cart pages, the cart drawer and the checkout summary
read it from here, so none of them falls back to the store currency in a secondary market."""

from dataclasses import dataclass

from frappe.utils.data import flt

from commera.localization.formatter import get_money_precision
from commera.localization.market_prices import MarketPrices
from commera.utils import get_currency_symbol


@dataclass(frozen=True)
class CartCurrency:
	code: str
	# HTML for some currencies (SAR draws an icon): print it as is, never escaped.
	symbol: str
	precision: int

	@classmethod
	def of(cls, quotation=None) -> "CartCurrency":
		"""The quotation's currency, else the request market's: a cart without a quotation (a guest's,
		or the cart page's server cart) is priced in the market of the request."""
		code = (quotation and quotation.get("currency")) or MarketPrices.current().currency
		return cls(code, get_currency_symbol(code), get_money_precision(code))

	def amount(self, value: float | None) -> str:
		"""The digits without the symbol, as the page's JavaScript prints them with toFixed."""
		return f"{flt(value):.{self.precision}f}"


def get_cart_currency(quotation=None) -> CartCurrency:
	return CartCurrency.of(quotation)
