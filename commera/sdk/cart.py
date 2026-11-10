import frappe
from frappe import _
from frappe.utils.data import cint, cstr, flt

from commera.api.payments import cart_write_lock, save_cart_quotation, validate_cart_is_not_in_checkout
from commera.api.shipping import get_checkout_summary, reprice_shipping_discount
from commera.checkout_hooks import apply_plugin_fees
from commera.commera_ecommerce.doctype.commera_cart.commera_cart import CommeraCart, get_session_cart
from commera.core import _get_cart_quotation
from commera.discounts.allocations import get_allocations
from commera.guest import get_guest_cart_name, is_guest
from commera.localization.market_prices import MarketPrices
from commera.plugin_events import get_listed_items, get_plugin_fieldnames, validate_plugin_fieldnames
from commera.sdk.lines import LineProducts
from commera.sdk.types import Cart, CheckoutSummary, NewCartLine, PricedCart

__all__ = [
	"add_discount_code",
	"add_lines",
	"get_cart",
	"get_priced_cart",
	"remove_discount_code",
	"remove_lines",
	"set_cart_attributes",
	"set_cart_fields",
	"set_lines",
	"update_lines",
]


def get_cart() -> Cart | None:
	"""The session shopper's cart, a guest's included, or None when they have not started one."""
	quotation = _get_cart_quotation()
	if quotation.is_new():
		return None

	products = LineProducts([row.item_code for row in quotation.items])
	return {
		"name": quotation.name,
		"customer": quotation.party_name if quotation.quotation_to == "Customer" else None,
		"currency": quotation.currency,
		"items": [
			{
				"item_code": row.item_code,
				"title": products.get_title(row.item_code, row.item_name),
				"qty": flt(row.qty),
				"rate": flt(row.rate),
				"amount": flt(row.amount),
				"discount": flt(row.custom_code_discount) * flt(row.qty),
				"attributes": frappe.parse_json(row.custom_line_attributes or "{}"),
			}
			for row in quotation.items
		],
		"discounts": get_allocations(quotation),
		"attributes": frappe.parse_json(quotation.custom_cart_attributes or "{}"),
		"total": flt(quotation.total),
		"grand_total": flt(quotation.grand_total),
		"plugin_fields": {
			fieldname: quotation.get(fieldname) for fieldname in get_plugin_fieldnames("Quotation")
		},
	}


def set_cart_fields(values: dict) -> CheckoutSummary:
	"""Before checkout the fields wait on the server cart; a cart in payment is refused."""
	validate_plugin_fieldnames("Quotation", values)
	quotation = get_open_cart_quotation()
	if not quotation:
		cart = get_session_cart(create=True)
		cart.set_plugin_fields(values)
		cart.save(ignore_permissions=True)
		preview = cart.get_quotation_preview()
		apply_plugin_fees(preview)
		return get_checkout_summary(preview)

	with cart_write_lock(quotation):
		validate_cart_is_not_in_checkout(quotation.name)
		quotation.update(values)
		apply_plugin_fees(quotation)
		save_cart_quotation(quotation)
		return get_checkout_summary(quotation)


def get_open_cart_quotation():
	if is_guest():
		cart_name = get_guest_cart_name()
		return frappe.get_doc("Quotation", cart_name) if cart_name else None
	quotation = _get_cart_quotation()
	return None if quotation.is_new() else quotation


def set_cart_attributes(values: dict) -> PricedCart:
	"""None removes a key; attributes reach the order as `attributes`."""
	cart = get_session_cart(create=True)
	cart.set_attributes(values)
	return save_server_cart(cart)


def get_priced_cart() -> PricedCart | None:
	cart = get_session_cart()
	return price_cart(cart) if cart else None


class CartChangedError(frappe.ValidationError):
	pass


def add_lines(lines: list[NewCartLine]) -> PricedCart:
	"""Only items a published product sells. The storefront shows new lines on the shopper's next page
	load."""
	validate_items_for_sale(lines)
	cart = get_session_cart(create=True)
	cart.add_lines(lines)
	return save_server_cart(cart)


def set_lines(lines: list[dict], revision: int | None) -> PricedCart | None:
	"""Make the cart hold exactly `lines`: `{line_id, qty}` keeps a line (0 drops it), `{item_code, qty}` adds
	one, the rest go. `revision` is the one the caller read, None for no cart; refused while paying."""
	validate_quantities(lines)
	quotation = get_open_cart_quotation()
	if not quotation:
		return replace_lines(lines, revision)
	# The quotation lock comes before the server cart's, in the order checkout takes them.
	with cart_write_lock(quotation):
		validate_cart_is_not_in_checkout(quotation.name)
		return replace_lines(lines, revision)


def validate_quantities(lines: list[dict]):
	for line in lines:
		least = 0 if line.get("line_id") else 1
		if cint(line["qty"]) < least:
			frappe.throw(_("A kept line needs a quantity of 0 or more, and a new line 1 or more."))


def replace_lines(lines: list[dict], revision: int | None) -> PricedCart | None:
	cart = get_session_cart()
	if (cint(cart.revision) if cart else None) != revision:
		frappe.throw(_("The cart changed. Read it again and retry."), CartChangedError)
	cart = cart or get_session_cart(create=True)
	kept = {line["line_id"]: cint(line["qty"]) for line in lines if line.get("line_id")}
	for line_id in kept:
		cart.get_line(line_id)
	cart.update_lines([{"line_id": row.name, "qty": kept.get(row.name, 0)} for row in cart.lines])
	if new_lines := [line for line in lines if not line.get("line_id")]:
		validate_items_for_sale(new_lines)
		cart.add_lines(new_lines)
	if cart.is_new() and not cart.lines:
		return None
	return save_server_cart(cart)


def validate_items_for_sale(lines: list[dict]):
	item_codes = {cstr(line["item_code"]) for line in lines}
	if unlisted := item_codes - get_listed_items(list(item_codes), sellable_only=True):
		frappe.throw(_("{0} is not for sale.").format(", ".join(sorted(unlisted))))
	if unpriced := MarketPrices.current().get_unpriced(sorted(item_codes)):
		frappe.throw(
			_("{0} is not available in this market.").format(", ".join(sorted(unpriced))),
			title=_("Not Available"),
		)


def update_lines(lines: list[dict]) -> PricedCart:
	cart = get_existing_cart()
	cart.update_lines(lines)
	return save_server_cart(cart)


def remove_lines(line_ids: list[str]) -> PricedCart:
	cart = get_existing_cart()
	cart.remove_lines(line_ids)
	return save_server_cart(cart)


def add_discount_code(code: str) -> PricedCart:
	cart = get_existing_cart()
	cart.add_discount_code(code)
	return save_discount_codes(cart)


def remove_discount_code(code: str) -> PricedCart:
	cart = get_existing_cart()
	cart.remove_discount_code(code)
	return save_discount_codes(cart)


def save_discount_codes(cart: CommeraCart) -> PricedCart:
	"""Codes also go on an open checkout: it copies the cart's codes only when it is made."""
	if quotation := get_open_cart_quotation():
		with cart_write_lock(quotation):
			validate_cart_is_not_in_checkout(quotation.name)
			quotation.custom_discount_codes = cart.discount_codes
			# The delivery discount was chosen with the old codes.
			reprice_shipping_discount(quotation)
			save_cart_quotation(quotation)
	return save_server_cart(cart)


def get_existing_cart() -> CommeraCart:
	cart = get_session_cart()
	if not cart:
		frappe.throw(_("Add something to your cart first."), frappe.DoesNotExistError)
	return cart


def save_server_cart(cart: CommeraCart) -> PricedCart:
	cart.save(ignore_permissions=True)
	return price_cart(cart)


def price_cart(cart: CommeraCart) -> PricedCart:
	priced = cart.get_priced_cart()
	line_products = LineProducts([line["item_code"] for line in priced["lines"]])
	products = line_products.get_cart_products()
	for line in priced["lines"]:
		line["title"] = line_products.get_title(line["item_code"], line["title"])
		line["product"] = products.get(line["item_code"])
	priced["total_quantity"] = sum(line["qty"] for line in priced["lines"])
	return priced
