import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cstr, flt

from commera.checkout_hooks import PLUGIN_FEE_FIELD, apply_delivery_option_hooks, apply_plugin_fees
from commera.core import _get_cart_quotation
from commera.discounts.allocations import get_allocations, get_discount_rows, get_price_discount_rows
from commera.discounts.pricing import refresh_code_discounts
from commera.discounts.shipping import apply_shipping_discounts, set_shipping_discount
from commera.shipping.base_class import RateItem
from commera.shipping.pricing import get_charge_account as get_rule_account
from commera.shipping.pricing import get_charge_amount as get_option_charge_amount
from commera.shipping.pricing import has_delivery_options, quote_services
from commera.shipping.shipment import get_order_shipments
from commera.shipping.units import WEIGHT_IN_KG
from commera.shipping.utils import get_address_payload
from commera.utils import (
	COD_CHARGE_DESCRIPTION,
	get_charge_account_head,
	get_cod_configuration,
	get_free_delivery,
	validate_document_access,
)

# The Actual charge row the chosen option posts through, matched on description on re-selection.
DELIVERY_CHARGE_DESCRIPTION = "Delivery Charges"

# ponytail: one notional box for the whole cart, since commera has no parcel templates; swap for a
# Shipment Parcel Template on Commera Settings once packing rules matter more than a rate estimate.
DEFAULT_PARCEL_DIMENSIONS = {"length": 30.0, "width": 20.0, "height": 10.0}
DEFAULT_ITEM_WEIGHT_KG = 0.5


# Guest checkout: refuses any caller without a guest cart cookie, and is rate limited.
@frappe.whitelist(allow_guest=True)  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=100, seconds=60 * 60)
def get_shipping_options() -> dict:
	"""Delivery options priced for the cart's current shipping address.

	Never raises: checkout has to render even when the carrier is down.
	"""
	return get_cart_shipping_options(_get_cart_quotation())


def get_cart_shipping_options(quotation) -> dict:
	if not quotation or not quotation.items:
		return {"options": []}
	if quotation.custom_is_store_pickup:
		return {"options": [], "store_pickup": True}
	if not has_delivery_options():
		# The key predates shipping in core; clients read it as "the store prices delivery by its flat rule".
		return {"options": [], "connector_missing": True}
	if not quotation.shipping_address_name:
		return {"options": [], "address_missing": True}

	try:
		options = get_delivery_options(quotation)
	except Exception:
		# The carrier failed, so checkout falls back to the flat Shipping Rule and says so.
		frappe.log_error(title="Shipping options could not be quoted")
		return {"options": [], "unavailable": True}

	return {"options": options, "selected": quotation.custom_delivery_option}


def get_delivery_options(quotation) -> list[dict]:
	return apply_delivery_option_hooks(quotation, get_quoted_options(quotation), strict=False)


def get_quoted_options(quotation) -> list[dict]:
	"""Priced options for this cart. Each carrier's rates are cached in commera.shipping.rates."""
	return quote_options(quotation)


def get_store_shipping_rule() -> str | None:
	return frappe.get_cached_value("Commera Settings", "Commera Settings", "shipping_rule")


def quote_options(quotation) -> list[dict]:
	"""Live-quote every enabled delivery option for this cart.

	No origin is passed: one shared origin drops every option to its backup charge across countries.
	"""
	return quote_services(
		None,
		get_address_payload(quotation.shipping_address_name),
		get_cart_parcels(quotation),
		get_cart_context(quotation),
		cod=False,
		shipping_rule=get_store_shipping_rule(),
	)


def get_cart_context(quotation) -> dict:
	"""What the pricing engine needs to bracket a Shipping Rule band, and what a carrier gets to price."""
	items = get_cart_items(quotation)
	customer = quotation.party_name if quotation.quotation_to == "Customer" else None
	return {
		"currency": quotation.currency,
		"conversion_rate": flt(quotation.conversion_rate) or 1.0,
		"base_net_total": flt(quotation.base_net_total),
		"net_total": flt(quotation.net_total),
		"grand_total": flt(quotation.grand_total),
		"discount_amount": flt(quotation.discount_amount),
		"weight": get_items_weight(items),
		"declared_value": flt(quotation.net_total),
		"items": items,
		"customer": customer,
		"customer_group": frappe.get_cached_value("Customer", customer, "customer_group")
		if customer
		else None,
		"locale": frappe.local.lang,
	}


def get_cart_weight(quotation) -> float:
	return get_items_weight(get_cart_items(quotation))


def get_items_weight(items: list[RateItem]) -> float:
	"""Total weight in kg. An item with no weight counts as the default weight."""
	return flt(sum(item.qty * (item.weight or DEFAULT_ITEM_WEIGHT_KG) for item in items), 3)


def get_cart_items(quotation) -> list[RateItem]:
	"""The cart lines a carrier prices, with each Item's own weight. One query: this runs on every render."""
	item_codes = list({item.item_code for item in quotation.items})
	if not item_codes:
		return []

	rows = frappe.get_all(
		"Item",
		filters={"name": ("in", item_codes)},
		fields=["name", "weight_per_unit", "weight_uom", "variant_of"],
	)
	row_by_item = {row.name: row for row in rows}
	return [get_rate_item(item, row_by_item.get(item.item_code)) for item in quotation.items]


def get_rate_item(item, row) -> RateItem:
	return RateItem(
		item_code=item.item_code,
		item_name=cstr(item.item_name),
		product=(row and row.variant_of) or item.item_code,
		qty=abs(flt(item.qty)),
		weight=to_kg(row) if row else 0.0,
		rate=flt(item.rate),
	)


def to_kg(item_row) -> float:
	"""An Item's weight in kg. An unconvertible UOM counts as unknown, so the default weight applies."""
	unit = (item_row.weight_uom or "kg").strip().casefold()
	factor = WEIGHT_IN_KG.get(unit)
	if factor is None:
		return 0.0
	return flt(item_row.weight_per_unit) * factor


def get_cart_parcels(quotation) -> list[dict]:
	return [
		{
			**DEFAULT_PARCEL_DIMENSIONS,
			"weight": get_cart_weight(quotation) or DEFAULT_ITEM_WEIGHT_KG,
			"count": 1,
		}
	]


# Guest checkout: refuses any caller without a guest cart cookie, and is rate limited.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=100, seconds=60 * 60)
def set_delivery_option(delivery_option: str | None = None) -> dict:
	"""Persist the customer's choice and reprice the delivery fee server-side.

	The price comes from a fresh server-side quote, never the request: a client could ship for nothing.
	"""
	return save_delivery_option(_get_cart_quotation(), delivery_option)


def save_delivery_option(quotation, delivery_option: str | None) -> dict:
	from commera.api.payments import cart_write_lock, save_cart_quotation, validate_cart_is_not_in_checkout

	with cart_write_lock(quotation):
		validate_cart_is_not_in_checkout(quotation.name)

		if not delivery_option:
			clear_delivery_option(quotation)
			save_cart_quotation(quotation)
			return get_delivery_summary(quotation)

		if quotation.custom_is_store_pickup:
			frappe.throw(_("This order is a store pickup, so it has no delivery option."))

		option = find_option(quotation, delivery_option)
		if option.get("phone_required") and not get_shipping_phone(quotation):
			frappe.throw(_("{0} needs a phone number on the shipping address.").format(option["title"]))
		apply_delivery_option(quotation, option)
		save_cart_quotation(quotation)
		return get_delivery_summary(quotation)


def get_shipping_phone(quotation) -> str | None:
	address = quotation.shipping_address_name or quotation.customer_address
	return (address and frappe.db.get_value("Address", address, "phone")) or quotation.contact_mobile


def find_option(quotation, delivery_option: str) -> dict:
	for option in get_delivery_options(quotation):
		if option["title"] == delivery_option:
			return option
	frappe.throw(_("Delivery option {0} is not available for this address.").format(delivery_option))


def apply_delivery_option(quotation, option: dict):
	quotation.custom_delivery_option = option["title"]
	quotation.custom_delivery_charge = flt(option["amount"])
	quotation.custom_shipping_provider = option.get("provider")
	quotation.custom_shipping_service_code = option.get("service_code")
	set_shipping_discount(quotation, option)
	set_delivery_charge_row(quotation, flt(option["amount"]), option["title"])
	apply_plugin_fees(quotation)


def reprice_shipping_discount(quotation):
	# The option was priced on a prepaid cart; re-price it for the payment mode.
	if not quotation.custom_delivery_option:
		return
	option = {
		"title": quotation.custom_delivery_option,
		"amount": flt(quotation.custom_delivery_charge) + flt(quotation.custom_shipping_discount),
		"provider": quotation.custom_shipping_provider,
		"service_code": quotation.custom_shipping_service_code,
	}
	apply_delivery_option(quotation, apply_shipping_discounts(quotation, [option])[0])


def clear_delivery_option(quotation):
	quotation.custom_delivery_option = None
	quotation.custom_delivery_charge = 0
	quotation.custom_shipping_provider = None
	quotation.custom_shipping_service_code = None
	set_shipping_discount(quotation, None)
	remove_delivery_charge_row(quotation)
	quotation.calculate_taxes_and_totals()


def set_delivery_charge_row(quotation, amount: float, title: str):
	"""Replace the delivery fee with an Actual charge row for the chosen option.

	The Shipping Rule's row is dropped first: clearing only the link leaves its tax row and double-charges.
	"""
	remove_shipping_rule_row(quotation)
	quotation.shipping_rule = None
	remove_delivery_charge_row(quotation)

	if amount > 0:
		quotation.append(
			"taxes",
			{
				"doctype": "Sales Taxes and Charges",
				"description": f"{DELIVERY_CHARGE_DESCRIPTION} - {title}",
				"charge_type": "Actual",
				"account_head": get_charge_account(get_store_shipping_rule()),
				"tax_amount": amount,
				# ERPNext refuses an inclusive Actual charge, and a site default of 1 would fail checkout.
				"included_in_print_rate": 0,
			},
		)

	quotation.calculate_taxes_and_totals()


def remove_delivery_charge_row(quotation):
	quotation.taxes = [
		row for row in quotation.taxes if not (row.description or "").startswith(DELIVERY_CHARGE_DESCRIPTION)
	]
	reindex_taxes(quotation)


def remove_shipping_rule_row(quotation):
	"""Drop the tax row ERPNext's Shipping Rule appended, identified the way ERPNext identifies it.

	Matched on charge_type, account_head and cost_center: the description is renamed and translated.
	"""
	rule = get_shipping_rule_accounts(quotation.shipping_rule)
	if not rule:
		return

	quotation.taxes = [row for row in quotation.taxes if not is_shipping_rule_row(row, rule)]
	reindex_taxes(quotation)


def get_shipping_rule_accounts(shipping_rule: str | None):
	if not shipping_rule:
		return None
	return frappe.get_cached_value("Shipping Rule", shipping_rule, ["account", "cost_center"], as_dict=True)


def is_shipping_rule_row(row, rule) -> bool:
	return bool(
		rule
		and row.charge_type == "Actual"
		and row.account_head == rule.account
		and row.cost_center == rule.cost_center
	)


def get_charge_lines(taxes, shipping_rule: str | None) -> dict:
	"""Split a charge table into delivery, the COD fee, plugin fees and the taxes a shopper sees by their own names.

	The Shipping Rule row is matched on account and cost centre because its description is translated.
	"""
	rule = get_shipping_rule_accounts(shipping_rule)
	charge_lines = {"shipping": 0.0, "cod_charge": 0.0, "plugin_fees": [], "taxes": []}
	for row in taxes:
		description = cstr(row.description).strip()
		# First: an app names its own fee, so its description can look like any other charge.
		if row.get(PLUGIN_FEE_FIELD):
			charge_lines["plugin_fees"].append({"description": description, "amount": flt(row.tax_amount)})
		elif description == COD_CHARGE_DESCRIPTION.strip():
			charge_lines["cod_charge"] += flt(row.tax_amount)
		elif description.startswith(DELIVERY_CHARGE_DESCRIPTION) or is_shipping_rule_row(row, rule):
			charge_lines["shipping"] += flt(row.tax_amount)
		else:
			charge_lines["taxes"].append({"description": description, "amount": flt(row.tax_amount)})
	return charge_lines


def get_charge_amount(quotation) -> float:
	return flt(quotation.grand_total if quotation.is_rounded_total_disabled() else quotation.rounded_total)


def get_checkout_summary(quotation) -> dict:
	"""The charges payment will apply, priced on an unsaved copy so showing them never rewrites the cart."""
	preview = frappe.get_doc(quotation.as_dict())
	if preview.custom_is_store_pickup:
		clear_pickup_charges(preview)
	summary = get_charge_summary(preview)

	# A prepaid-only discount drops off, and a cash-on-delivery one comes on, before the fee is judged.
	preview.flags.commera_payment_kind = "cod"
	reprice_shipping_discount(preview)
	refresh_code_discounts(preview)
	cod_charge = get_cod_charge(preview)
	if cod_charge:
		account_head = frappe.get_cached_value("Commera Settings", "Commera Settings", "charge_account_head")
		add_cod_charge(preview, cod_charge, account_head)
	summary["cash_on_delivery"] = get_charge_summary(preview)
	return summary


def get_charge_summary(quotation) -> dict:
	charge_lines = get_charge_lines(quotation.taxes, quotation.shipping_rule)
	charges = charge_lines["shipping"] + charge_lines["cod_charge"]
	charges += sum(line["amount"] for line in charge_lines["taxes"] + charge_lines["plugin_fees"])
	discount_amount = flt(quotation.discount_amount)
	# Derived rather than read: with a Grand Total discount the stored net_total is already partly discounted.
	subtotal = flt(flt(quotation.grand_total) + discount_amount - charges, quotation.precision("grand_total"))
	line_discount = sum(flt(item.get("custom_code_discount")) * flt(item.qty) for item in quotation.items)
	return {
		"subtotal": subtotal,
		"items_total": flt(subtotal + line_discount, quotation.precision("grand_total")),
		"discounts": get_price_discount_rows(quotation),
		"shipping_discounts": get_discount_rows(get_allocations(quotation), ("Shipping",)),
		"shipping": charge_lines["shipping"],
		"cod_charge": charge_lines["cod_charge"],
		"plugin_fees": charge_lines["plugin_fees"],
		"taxes": charge_lines["taxes"],
		"discount_amount": discount_amount,
		"rounding_adjustment": flt(quotation.rounding_adjustment),
		"total": get_charge_amount(quotation),
		**get_free_delivery(quotation),
	}


def clear_pickup_charges(quotation):
	quotation.shipping_rule = None
	quotation.taxes = [row for row in quotation.taxes if row.get(PLUGIN_FEE_FIELD)]
	reindex_taxes(quotation)
	quotation.calculate_taxes_and_totals()


def get_cod_charge(quotation) -> float:
	applicable_below, cod_charge = get_cod_configuration()
	if not applicable_below or not cod_charge or flt(applicable_below) < get_charge_amount(quotation):
		return 0.0
	return flt(cod_charge)


def add_cod_charge(quotation, cod_charge: float, account_head: str | None):
	quotation.append(
		"taxes",
		{
			"doctype": "Sales Taxes and Charges",
			"description": COD_CHARGE_DESCRIPTION,
			"charge_type": "Actual",
			"account_head": account_head,
			"tax_amount": cod_charge,
			# ERPNext's validate_inclusive_tax refuses an inclusive Actual charge; pinned against a site default of 1.
			"included_in_print_rate": 0,
		},
	)
	quotation.calculate_taxes_and_totals()


def get_order_charge_lines(sales_order: str, shipping_rule: str | None) -> dict:
	return get_charge_lines(read_order_taxes([sales_order]).get(cstr(sales_order), []), shipping_rule)


def read_order_taxes(order_names: list) -> dict[str, list]:
	taxes_by_order = {}
	for row in frappe.get_all(
		"Sales Taxes and Charges",
		filters={"parent": ["in", [cstr(name) for name in order_names]], "parenttype": "Sales Order"},
		fields=[
			"parent",
			"description",
			"charge_type",
			"account_head",
			"cost_center",
			"tax_amount",
			PLUGIN_FEE_FIELD,
		],
		order_by="idx asc",
	):
		taxes_by_order.setdefault(cstr(row.parent), []).append(row)
	return taxes_by_order


def reindex_taxes(quotation):
	for index, row in enumerate(quotation.taxes, start=1):
		row.idx = index


def get_charge_account(shipping_rule: str | None) -> str:
	"""The store Shipping Rule's account when it has one, else the store's charge account head."""
	return get_rule_account(shipping_rule) or get_charge_account_head()


def get_delivery_summary(quotation) -> dict:
	return {
		"delivery_option": quotation.custom_delivery_option,
		"delivery_charge": flt(quotation.custom_delivery_charge),
		"grand_total": get_charge_amount(quotation),
		"currency": quotation.currency,
		"checkout_summary": get_checkout_summary(quotation),
	}


def reprice_selected_option(quotation) -> bool:
	"""Re-apply the stored delivery option to the cart, as it stands now.

	Returns whether an option was applied, so the caller can fall back to the flat Shipping Rule.
	"""
	if not quotation.custom_delivery_option:
		return False

	from commera.api.payments import CheckoutPriceChangedError

	options = get_quoted_options(quotation)
	if not any(option["title"] == quotation.custom_delivery_option for option in options):
		# No longer quotable for this address, so fall back to its stored price rather than lose the charge.
		amount = get_option_charge_amount(
			quotation.custom_delivery_option,
			get_cart_context(quotation),
			# Before its shipping discount, which the hooks below take off again.
			quoted_amount=flt(quotation.custom_delivery_charge) + flt(quotation.custom_shipping_discount),
			shipping_rule=get_store_shipping_rule(),
		)
		options = [
			*options,
			{
				"title": quotation.custom_delivery_option,
				"amount": amount,
				"provider": quotation.custom_shipping_provider,
				"service_code": quotation.custom_shipping_service_code,
			},
		]

	options = apply_delivery_option_hooks(quotation, options, strict=bool(quotation.flags.strict_plugin_fees))
	for option in options:
		if option["title"] == quotation.custom_delivery_option:
			apply_delivery_option(quotation, option)
			return True

	frappe.throw(
		_("Your delivery option is no longer available. Please choose another one."),
		title=_("Delivery Option Changed"),
		exc=CheckoutPriceChangedError,
	)


def copy_delivery_option_to_order(quotation_name: str, sales_order) -> None:
	"""Carry the paid-for delivery choice onto the Sales Order, so fulfilment books that exact service."""
	choice = frappe.db.get_value(
		"Quotation",
		quotation_name,
		[
			"custom_delivery_option",
			"custom_delivery_charge",
			"custom_shipping_provider",
			"custom_shipping_service_code",
		],
		as_dict=True,
	)
	if not (choice and choice.custom_delivery_option):
		return

	sales_order.custom_delivery_option = choice.custom_delivery_option
	sales_order.custom_delivery_charge = flt(choice.custom_delivery_charge)
	sales_order.custom_shipping_provider = choice.custom_shipping_provider
	sales_order.custom_shipping_service_code = choice.custom_shipping_service_code


# Guests read tracking only with the order's private link key; validate_document_access compares it.
@frappe.whitelist(allow_guest=True)  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=120, seconds=60 * 60)
def get_order_tracking(sales_order: str, key: str | None = None) -> dict:
	"""Customer-facing tracking for one of their own orders, or one whose private link they hold."""
	validate_document_access("Sales Order", sales_order, key)

	shipments = get_order_shipments(
		sales_order, fields=["name", "awb_number", "carrier", "custom_shipment_status", "tracking_url"]
	)
	if not shipments or not shipments[0].awb_number:
		return {"has_tracking": False}

	shipment = shipments[0]
	events = frappe.get_all(
		"Shipping Tracking Event",
		filters={"parent": shipment.name, "parenttype": "Shipment"},
		fields=["timestamp", "status", "location", "message"],
		order_by="timestamp desc",
	)
	return {
		"has_tracking": True,
		"awb": shipment.awb_number,
		"carrier": shipment.carrier,
		"status": shipment.custom_shipment_status,
		"tracking_url": shipment.tracking_url,
		"events": events,
	}
