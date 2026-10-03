from datetime import date
from typing import Any, TypedDict

__all__ = [
	"Cart",
	"CartLine",
	"CatalogItem",
	"Charge",
	"ChargeSummary",
	"CheckoutSummary",
	"Order",
	"OrderLine",
	"Stage",
]


class Charge(TypedDict):
	description: str
	amount: float


class Stage(TypedDict):
	key: str
	label: str


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


class Order(TypedDict):
	"""Money is in `currency`; the `base_` totals are in the company currency."""

	name: str | int
	customer: str
	customer_name: str
	email: str | None
	phone: str | None
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
	app_fees: list[Charge]
	items: list[OrderLine]
	tags: list[str]
	app_fields: dict[str, Any]


class CartLine(TypedDict):
	item_code: str
	title: str
	qty: float
	rate: float
	amount: float


class Cart(TypedDict):
	name: str
	customer: str | None
	currency: str
	items: list[CartLine]
	total: float
	grand_total: float
	app_fields: dict[str, Any]


class ChargeSummary(TypedDict):
	subtotal: float
	shipping: float
	cod_charge: float
	app_fees: list[Charge]
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
