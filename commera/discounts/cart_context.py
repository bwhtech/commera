from dataclasses import dataclass, field

import frappe
from frappe.utils.data import cint, cstr, flt

from commera.api.cart import get_cart_price


@dataclass
class CartContext:
	"""What a discount's conditions read about a cart, Sales Order or Sales Invoice."""

	doc: object
	payment_kind: str
	customer: str | None
	customer_group: str | None
	email: str | None
	phone: str | None
	sale_by_item_code: dict = field(default_factory=dict)

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
	# Imported here: commera.api.payments imports the cart, which imports this module.
	from commera.api.payments import is_cod

	if doc.flags.commera_payment_kind:
		return doc.flags.commera_payment_kind
	return "cod" if is_cod(doc.get("custom_ecommerce_payment_mode")) else "prepaid"
