from datetime import date
from typing import Any, TypedDict

__all__ = [
	"Address",
	"Cart",
	"CartLine",
	"CartLineProduct",
	"CatalogItem",
	"Charge",
	"ChargeSummary",
	"CheckoutSummary",
	"Collection",
	"ContentPage",
	"CustomerAddress",
	"CustomerProfile",
	"Discount",
	"DiscountAllocation",
	"DiscountInput",
	"FacetValue",
	"FooterSection",
	"MenuItem",
	"NewCartLine",
	"Order",
	"OrderLine",
	"PricedCart",
	"PricedCartLine",
	"Product",
	"ProductCard",
	"ProductFacets",
	"ProductOption",
	"ProductOptionValue",
	"ProductPage",
	"ProductVariant",
	"Rating",
	"Shop",
	"ShopperOrder",
	"ShopperOrderPage",
	"Sitemap",
	"SitemapEntry",
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
	discount: float
	attributes: dict[str, str]


class ShopperOrder(TypedDict):
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
	plugin_fields: dict[str, Any]
	discounts: list["DiscountAllocation"]
	attributes: dict[str, str]


class Order(ShopperOrder):
	tags: list[str]


class ShopperOrderPage(TypedDict):
	orders: list[ShopperOrder]
	total: int
	page: int
	page_size: int


class CustomerAddress(Address):
	address_type: str
	email_id: str | None
	is_primary_address: bool
	is_shipping_address: bool


class CustomerProfile(TypedDict):
	email: str
	first_name: str
	last_name: str | None
	full_name: str
	phone: str | None


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
	# Whether the line goes to checkout; True when left out.
	selected: bool


class CartLineProduct(TypedDict):
	"""The published product that sells a cart line's item."""

	handle: str
	title: str
	# The size.
	variant_title: str
	image: str | None


class PricedCartLine(TypedDict):
	line_id: str
	item_code: str
	title: str
	qty: int
	selected: bool
	attributes: dict[str, str]
	price: float
	rate: float
	# Per unit.
	code_discount: float
	# The Commera Discount on this line.
	discount: str | None
	amount: float
	# None when no published product sells the item any more.
	product: CartLineProduct | None


class DiscountRow(TypedDict):
	# The code, or the automatic discount's title; None for a discount ERPNext gave on its own.
	label: str | None
	amount: float


class PricedCart(TypedDict):
	"""Before shipping and tax."""

	name: str
	version: str
	attributes: dict[str, str]
	currency: str
	# {"code", "title", "discount_class", "applied", "reason"}; reason says why an unapplied code gives nothing.
	discount_codes: list[dict]
	# {"title", "amount"} of each automatic discount the cart gets.
	automatic_discounts: list[dict]
	lines: list[PricedCartLine]
	total_quantity: int
	discounts: list[DiscountRow]
	subtotal: float
	order_discount: float
	total: float
	# The store Shipping Rule's free band, judged after every discount; None when it has none.
	free_delivery_above: float | None
	free_delivery_shortfall: float


class ChargeSummary(TypedDict):
	subtotal: float
	# Before discount codes; see discounts.
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
	free_delivery_above: float | None
	free_delivery_shortfall: float


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


class Rating(TypedDict):
	average: float
	count: int


class ProductCard(TypedDict):
	"""A published product as a shopper sees it in a grid. Image paths are site-relative or absolute."""

	id: str
	handle: str
	title: str
	vendor: str | None
	color: str | None
	image: str | None
	hover_image: str | None
	currency: str
	price: float
	compare_at_price: float | None
	available: bool
	rating: Rating
	updated_at: str | None


class FacetValue(TypedDict):
	value: str
	# Products with this value under every other selected filter.
	count: int


class ProductFacets(TypedDict):
	brands: list[FacetValue]
	colors: list[FacetValue]
	sizes: list[FacetValue]
	price: dict[str, float]


class ProductPage(TypedDict):
	products: list[ProductCard]
	total: int
	page: int
	page_size: int
	facets: ProductFacets


class ProductOptionValue(TypedDict, total=False):
	name: str
	# Colour values only: the sibling product's handle, whether it is this one, and its stock and swatch.
	handle: str
	selected: bool
	available: bool
	swatch: dict | None


class ProductOption(TypedDict):
	name: str
	values: list[ProductOptionValue]


class ProductVariant(TypedDict):
	"""One size of a product."""

	id: str
	title: str
	price: float
	compare_at_price: float | None
	available: bool
	# None when the item is sold without stock tracking.
	quantity_available: float | None


class Product(TypedDict):
	"""One colour of a style: sibling colours are the colour option, sizes are the variants."""

	id: str
	handle: str
	title: str
	vendor: str | None
	color: str | None
	description_html: str
	images: list[str]
	collection: dict | None
	currency: str
	price: float
	available: bool
	options: list[ProductOption]
	variants: list[ProductVariant]
	selected_variant_id: str | None
	rating: Rating
	seo: dict
	updated_at: str


class Collection(TypedDict):
	"""An Item Group that holds a published product."""

	handle: str
	title: str
	image: str | None
	updated_at: str


class MenuItem(TypedDict):
	"""`type` is "collection" (target: a collection handle), "brand" (target: the brand), "url" (target:
	the URL) or "all" (every product); a node with no link has type None."""

	title: str
	type: str | None
	target: str | None
	items: list["MenuItem"]


class FooterSection(TypedDict):
	title: str
	links: list[dict[str, str]]


class Shop(TypedDict):
	name: str
	description: str
	currency: str
	logo: str
	favicon: str
	menu: list[MenuItem]
	footer: list[FooterSection]


class ContentPage(TypedDict):
	handle: str
	title: str
	body_html: str
	seo: dict
	updated_at: str


class SitemapEntry(TypedDict):
	handle: str
	updated_at: str


class SitemapPage(TypedDict):
	# Handles of each returned kind.
	total: dict[str, int]
	page: int
	page_size: int


class Sitemap(SitemapPage, total=False):
	"""Only the asked kind, or every kind when none is asked."""

	products: list[SitemapEntry]
	collections: list[SitemapEntry]
	pages: list[SitemapEntry]
