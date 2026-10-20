from datetime import date
from typing import Any, TypedDict

__all__ = [
	"Address",
	"Cart",
	"CartLine",
	"CatalogItem",
	"Charge",
	"ChargeSummary",
	"CheckoutSummary",
	"Discount",
	"DiscountAllocation",
	"DiscountInput",
	"NewCartLine",
	"Order",
	"OrderLine",
	"PricedCart",
	"PricedCartLine",
	"Stage",
]


class Charge(TypedDict):
	description: str
	amount: float


class Stage(TypedDict):
	key: str
	label: str


class Address(TypedDict):
	name: str
	address_title: str | None
	address_line1: str
	address_line2: str | None
	city: str
	state: str | None
	pincode: str | None
	country: str
	phone: str | None


class OrderLine(TypedDict):
	line_id: str
	item_code: str
	title: str
	size: str | None
	qty: float
	delivered_qty: float
	rate: float
	amount: float
	image: str | None
	# The whole line's discount from a discount code, an automatic discount or an app.
	discount: float
	attributes: dict[str, str]


class Order(TypedDict):
	"""Money is in `currency`; the `base_` totals are in the company currency."""

	name: str | int
	customer: str
	customer_name: str
	email: str | None
	phone: str | None
	# The order's shipping address, else its billing one; None when it has neither.
	shipping_address: Address | None
	placed_on: date
	order_type: str
	currency: str
	total: float
	net_total: float
	grand_total: float
	rounded_total: float
	base_grand_total: float
	base_rounded_total: float
	payment_mode: str | None
	is_paid: bool
	is_cancelled: bool
	# The stored ladder value that order events fire on, e.g. "Shipped".
	status: str | None
	# The dashboard's badge for the order, so a card matches the order screen.
	stage: Stage
	plugin_fees: list[Charge]
	items: list[OrderLine]
	tags: list[str]
	plugin_fields: dict[str, Any]
	discounts: list["DiscountAllocation"]
	attributes: dict[str, str]


class CartLine(TypedDict):
	item_code: str
	title: str
	qty: float
	rate: float
	amount: float
	discount: float
	attributes: dict[str, str]


class Cart(TypedDict):
	name: str
	customer: str | None
	currency: str
	items: list[CartLine]
	discounts: list["DiscountAllocation"]
	attributes: dict[str, str]
	total: float
	grand_total: float
	plugin_fields: dict[str, Any]


class DiscountInput(TypedDict, total=False):
	"""Commera Discount fields. Only `discount_type` is required; see the doctype for every rule."""

	title: str
	# "Code" or "Automatic".
	method: str
	# "Amount Off Products", "Amount Off Order", "Buy X Get Y" or "Free Shipping".
	discount_type: str
	# "Percentage" or "Fixed Amount".
	value_type: str
	value: float
	maximum_discount: float
	# {"role": "Applies To" | "Excluded" | "Buys" | "Gets", "target_type": "Item" | "Item Group" | "Brand", "target"}
	targets: list[dict]
	tiers: list[dict]
	starts_on: date
	ends_on: date | None


class Discount(DiscountInput, total=False):
	name: str
	# Active, Scheduled, Expired, Used Up or Disabled.
	status: str
	# Product, Order or Shipping.
	discount_class: str
	codes: list[str]
	times_used: int
	discount_given: float
	sales: float


class DiscountAllocation(TypedDict):
	discount: str
	code: str | None
	title: str
	# Product, Order or Shipping.
	discount_class: str
	amount: float
	# The cart line's idx for a product discount.
	line: int | None


class NewCartLine(TypedDict, total=False):
	item_code: str
	qty: int
	attributes: dict[str, str]


class PricedCartLine(TypedDict):
	line_id: str
	item_code: str
	title: str
	qty: int
	attributes: dict[str, str]
	price: float
	rate: float
	# Per unit, from the best product discount code on the line.
	code_discount: float
	discount_code: str | None
	amount: float


class DiscountRow(TypedDict):
	# The code, or the automatic discount's title; None for a discount ERPNext gave on its own.
	label: str | None
	amount: float


class PricedCart(TypedDict):
	"""The server cart priced like checkout, before shipping and tax."""

	name: str
	version: str
	attributes: dict[str, str]
	currency: str
	# {"code", "class"}, where class is "Product" or "Order".
	discount_codes: list[dict]
	lines: list[PricedCartLine]
	# Line and order discounts by code or automatic discount.
	discounts: list[DiscountRow]
	subtotal: float
	order_discount: float
	total: float


class ChargeSummary(TypedDict):
	subtotal: float
	# The lines before discount codes; `discounts` lists what came off them and off the order.
	items_total: float
	discounts: list[DiscountRow]
	shipping_discounts: list[DiscountRow]
	shipping: float
	cod_charge: float
	plugin_fees: list[Charge]
	taxes: list[Charge]
	discount_amount: float
	rounding_adjustment: float
	total: float


class CheckoutSummary(ChargeSummary):
	cash_on_delivery: ChargeSummary


class CatalogItem(TypedDict):
	item_code: str
	title: str
	product: str
	is_listed: bool
	price: float | None
	list_price: float | None
	currency: str
	available_qty: float
	# Drop-shipped or not stock-tracked: sellable whatever available_qty says.
	unlimited: bool
