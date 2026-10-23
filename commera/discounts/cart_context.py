from dataclasses import dataclass, field

import frappe
from erpnext.setup.utils import get_exchange_rate
from frappe.utils.data import cint, cstr, flt

from commera.api.cart import get_cart_price
from commera.core import is_cod


@dataclass
class CartContext:
	doc: object
	payment_kind: str
	customer: str | None
	customer_group: str | None
	email: str | None
	phone: str | None
	sale_by_item_code: dict = field(default_factory=dict)
	exchange_rates: dict = field(default_factory=dict)
	offered_option: dict | None = None

	@property
	def items(self) -> list:
		return self.doc.items

	@property
	def currency(self) -> str:
		return self.doc.currency

	@property
	def subtotal(self) -> float:
		return sum(flt(item.amount) for item in self.items)

	@property
	def quantity(self) -> int:
		return sum(cint(item.qty) for item in self.items)

	@property
	def delivery_option(self) -> dict | None:
		# Priced before any shipping discount.
		if self.offered_option:
			return self.offered_option
		if not self.doc.get("custom_delivery_option"):
			return None
		return {
			"title": self.doc.custom_delivery_option,
			"amount": flt(self.doc.get("custom_delivery_charge"))
			+ flt(self.doc.get("custom_shipping_discount")),
		}

	def get_exchange_rate(self, currency: str | None) -> float:
		currency = currency or frappe.get_cached_value("Company", self.doc.company, "default_currency")
		if currency == self.currency:
			return 1.0
		if currency not in self.exchange_rates:
			self.exchange_rates[currency] = flt(
				get_exchange_rate(currency, self.currency, self.doc.get("transaction_date"), "for_selling")
			)
		return self.exchange_rates[currency]

	def convert(self, amount: float, currency: str | None) -> float:
		return flt(amount) * self.get_exchange_rate(currency) if flt(amount) else 0.0

	def is_on_sale(self, item_code: str) -> bool:
		if item_code not in self.sale_by_item_code:
			settings = frappe.get_cached_doc("Commera Settings")
			regular_price, price = get_cart_price(
				item_code, settings.get_default_price_list(), settings.get_sale_price_list()
			)
			self.sale_by_item_code[item_code] = flt(price) < flt(regular_price)
		return self.sale_by_item_code[item_code]


def get_cart_context(doc) -> CartContext:
	customer = doc.get("customer") or (doc.party_name if doc.get("quotation_to") == "Customer" else None)
	return CartContext(
		doc=doc,
		payment_kind=get_payment_kind(doc),
		customer=customer,
		customer_group=frappe.get_cached_value("Customer", customer, "customer_group") if customer else None,
		email=cstr(doc.get("contact_email")).strip().lower() or None,
		phone=doc.get("contact_mobile") or doc.get("contact_phone") or None,
	)


def get_payment_kind(doc) -> str:
	"""A cart is priced as prepaid until checkout says otherwise; an order knows how it is paid."""
	if doc.flags.commera_payment_kind:
		return doc.flags.commera_payment_kind
	return "cod" if is_cod(doc.get("custom_ecommerce_payment_mode")) else "prepaid"
