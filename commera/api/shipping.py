import frappe
from frappe import _
from frappe.utils.data import cstr, flt, sha256_hash

from commera.core import _get_cart_quotation
from commera.utils import COD_CHARGE_DESCRIPTION, get_cod_configuration, validate_document_access

# The Actual charge row the chosen option posts through, matched on description on re-selection.
DELIVERY_CHARGE_DESCRIPTION = "Delivery Charges"

# ponytail: one notional box for the whole cart, since commera has no parcel templates; swap for a
# Shipment Parcel Template on Commera Settings once packing rules matter more than a rate estimate.
DEFAULT_PARCEL_DIMENSIONS = {"length": 30.0, "width": 20.0, "height": 10.0}
DEFAULT_ITEM_WEIGHT_KG = 0.5

RATES_CACHE_TTL_SECONDS = 30 * 60


def is_connector_installed() -> bool:
	"""bwh_shipping is a soft dependency: without it the storefront keeps the flat Shipping Rule."""
	return "bwh_shipping" in frappe.get_installed_apps()


@frappe.whitelist()
def get_shipping_options() -> dict:
	"""Delivery options priced for the cart's current shipping address.

	Never raises: checkout has to render even when the carrier is down.
	"""
	quotation = _get_cart_quotation()
	if not quotation or not quotation.items:
		return {"options": []}
	if quotation.custom_is_store_pickup:
		return {"options": [], "store_pickup": True}
	if not is_connector_installed():
		return {"options": [], "connector_missing": True}
	if not quotation.shipping_address_name:
		return {"options": [], "address_missing": True}

	try:
		options = get_quoted_options(quotation)
	except Exception:
		# The connector failed, so checkout falls back to the flat Shipping Rule and says so.
		frappe.log_error(title="Shipping options could not be quoted")
		return {"options": [], "unavailable": True}

	return {"options": options, "selected": quotation.custom_delivery_option}


def get_quoted_options(quotation) -> list[dict]:
	"""Priced options for this cart, cached against a fingerprint of everything that changes the price.

	Everything that changes a quote is in the key, so a stale price cannot outlive what it priced.
	"""
	cache_key = f"commera:shipping_rates:{quotation.name}:{get_cart_fingerprint(quotation)}"
	cached = frappe.cache.get_value(cache_key)
	if cached is not None:
		return cached

	options = quote_options(quotation)
	frappe.cache.set_value(cache_key, options, expires_in_sec=RATES_CACHE_TTL_SECONDS)
	return options


def get_cart_fingerprint(quotation) -> str:
	items = ";".join(f"{item.item_code}x{flt(item.qty)}" for item in quotation.items)
	parts = (
		quotation.shipping_address_name or "",
		items,
		str(flt(quotation.net_total)),
		quotation.currency or "",
		get_services_stamp(),
	)
	return sha256_hash("|".join(parts))[:12]


def get_services_stamp() -> str:
	"""When the delivery options were last edited.

	In the fingerprint because the cart cannot see a desk edit, which would otherwise stay cached.
	"""
	latest = frappe.get_all("Shipping Service", fields=["modified"], order_by="modified desc", limit=1)
	return str(latest[0].modified) if latest else ""


def quote_options(quotation) -> list[dict]:
	"""Live-quote every enabled delivery option for this cart.

	No origin is passed: one shared origin drops every option to its backup charge across countries.
	"""
	from bwh_shipping.bwh_shipping.pricing import quote_services
	from bwh_shipping.bwh_shipping.utils import get_address_payload

	return quote_services(
		None,
		get_address_payload(quotation.shipping_address_name),
		get_cart_parcels(quotation),
		get_cart_context(quotation),
		cod=False,
	)


def get_cart_context(quotation) -> dict:
	"""The figures the pricing engine needs to bracket a Shipping Rule band and convert its amount."""
	return {
		"currency": quotation.currency,
		"conversion_rate": flt(quotation.conversion_rate) or 1.0,
		"base_net_total": flt(quotation.base_net_total),
		"net_total": flt(quotation.net_total),
		"weight": get_cart_weight(quotation),
		"declared_value": flt(quotation.net_total),
	}


def get_cart_weight(quotation) -> float:
	"""Total cart weight in kg, from each item's own weight where ERPNext knows it.

	One query, not a get_doc per line: this runs on every checkout render.
	"""
	item_codes = list({item.item_code for item in quotation.items})
	if not item_codes:
		return 0.0

	weights = frappe.get_all(
		"Item",
		filters={"name": ("in", item_codes)},
		fields=["name", "weight_per_unit", "weight_uom"],
	)
	weight_by_item = {row.name: row for row in weights}

	total = 0.0
	for item in quotation.items:
		row = weight_by_item.get(item.item_code)
		unit_weight = to_kg(row) if row else 0.0
		total += abs(flt(item.qty)) * (unit_weight or DEFAULT_ITEM_WEIGHT_KG)
	return flt(total, 3)


def to_kg(item_row) -> float:
	"""An Item's weight in kg. An unconvertible UOM counts as unknown, so the default weight applies."""
	from bwh_shipping.units import WEIGHT_IN_KG

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


@frappe.whitelist()
def set_delivery_option(delivery_option: str | None = None) -> dict:
	"""Persist the customer's choice and reprice the delivery fee server-side.

	The price comes from a fresh server-side quote, never the request: a client could ship for nothing.
	"""
	from commera.api.payments import cart_write_lock, save_cart_quotation, validate_cart_is_not_in_checkout

	quotation = _get_cart_quotation()

	with cart_write_lock(quotation):
		validate_cart_is_not_in_checkout(quotation.name)

		if not delivery_option:
			clear_delivery_option(quotation)
			save_cart_quotation(quotation)
			return get_delivery_summary(quotation)

		if quotation.custom_is_store_pickup:
			frappe.throw(_("This order is a store pickup, so it has no delivery option."))
		if not is_connector_installed():
			frappe.throw(_("Delivery options are not available on this store."))

		option = find_option(quotation, delivery_option)
		apply_delivery_option(quotation, option)
		save_cart_quotation(quotation)
		return get_delivery_summary(quotation)


def find_option(quotation, delivery_option: str) -> dict:
	for option in get_quoted_options(quotation):
		if option["title"] == delivery_option:
			return option
	frappe.throw(_("Delivery option {0} is not available for this address.").format(delivery_option))


def apply_delivery_option(quotation, option: dict):
	quotation.custom_delivery_option = option["title"]
	quotation.custom_delivery_charge = flt(option["amount"])
	quotation.custom_shipping_provider = option.get("provider")
	quotation.custom_shipping_service_code = option.get("service_code")
	set_delivery_charge_row(quotation, flt(option["amount"]), option["title"])


def clear_delivery_option(quotation):
	quotation.custom_delivery_option = None
	quotation.custom_delivery_charge = 0
	quotation.custom_shipping_provider = None
	quotation.custom_shipping_service_code = None
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
				"account_head": get_charge_account(title),
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
	"""Split a charge table into delivery, the COD fee and the taxes a shopper sees by their own names.

	The Shipping Rule row is matched on account and cost centre because its description is translated.
	"""
	rule = get_shipping_rule_accounts(shipping_rule)
	charge_lines = {"shipping": 0.0, "cod_charge": 0.0, "taxes": []}
	for row in taxes:
		description = cstr(row.description).strip()
		if description == COD_CHARGE_DESCRIPTION.strip():
			charge_lines["cod_charge"] += flt(row.tax_amount)
		elif description.startswith(DELIVERY_CHARGE_DESCRIPTION) or is_shipping_rule_row(row, rule):
			charge_lines["shipping"] += flt(row.tax_amount)
		else:
			charge_lines["taxes"].append({"description": description, "amount": flt(row.tax_amount)})
	return charge_lines


def get_charge_amount(quotation) -> float:
	# rounded_total is 0 when rounding is disabled on the document; grand_total is the billed figure then.
	return flt(quotation.rounded_total) or flt(quotation.grand_total)


def get_checkout_summary(quotation) -> dict:
	"""The charges payment will apply, priced on an unsaved copy so showing them never rewrites the cart."""
	preview = frappe.get_doc(quotation.as_dict())
	if preview.custom_is_store_pickup:
		clear_pickup_charges(preview)
	summary = get_charge_summary(preview)

	cod_charge = get_cod_charge(preview)
	if cod_charge:
		account_head = frappe.get_cached_value("Commera Settings", "Commera Settings", "charge_account_head")
		add_cod_charge(preview, cod_charge, account_head)
	summary["cash_on_delivery"] = get_charge_summary(preview)
	return summary


def get_charge_summary(quotation) -> dict:
	charge_lines = get_charge_lines(quotation.taxes, quotation.shipping_rule)
	charges = charge_lines["shipping"] + charge_lines["cod_charge"]
	charges += sum(tax["amount"] for tax in charge_lines["taxes"])
	discount_amount = flt(quotation.discount_amount)
	return {
		# Derived rather than read: with a Grand Total discount the stored net_total is already partly discounted.
		"subtotal": flt(
			flt(quotation.grand_total) + discount_amount - charges, quotation.precision("grand_total")
		),
		"shipping": charge_lines["shipping"],
		"cod_charge": charge_lines["cod_charge"],
		"taxes": charge_lines["taxes"],
		"discount_amount": discount_amount,
		"rounding_adjustment": flt(quotation.rounding_adjustment),
		"total": get_charge_amount(quotation),
	}


def clear_pickup_charges(quotation):
	quotation.shipping_rule = None
	quotation.taxes = []
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
	taxes = frappe.get_all(
		"Sales Taxes and Charges",
		filters={"parent": sales_order, "parenttype": "Sales Order"},
		fields=["description", "charge_type", "account_head", "cost_center", "tax_amount"],
		order_by="idx asc",
	)
	return get_charge_lines(taxes, shipping_rule)


def reindex_taxes(quotation):
	for index, row in enumerate(quotation.taxes, start=1):
		row.idx = index


def get_charge_account(title: str) -> str:
	"""The option's own Shipping Rule account when it has one, else the store's charge account head."""
	from bwh_shipping.bwh_shipping.pricing import get_charge_account as get_option_account

	account = get_option_account(title)
	if account:
		return account

	account = frappe.get_cached_value("Commera Settings", "Commera Settings", "charge_account_head")
	if not account:
		frappe.throw(_("Set a Charge Account Head in Commera Settings before charging for delivery."))
	return account


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
	if not (quotation.custom_delivery_option and is_connector_installed()):
		return False

	from bwh_shipping.bwh_shipping.pricing import get_charge_amount

	for option in get_quoted_options(quotation):
		if option["title"] == quotation.custom_delivery_option:
			apply_delivery_option(quotation, option)
			return True

	# No longer quotable for this address, so fall back to its stored price rather than lose the charge.
	amount = get_charge_amount(
		quotation.custom_delivery_option,
		get_cart_context(quotation),
		quoted_amount=flt(quotation.custom_delivery_charge) or None,
	)
	apply_delivery_option(
		quotation,
		{
			"title": quotation.custom_delivery_option,
			"amount": amount,
			"provider": quotation.custom_shipping_provider,
			"service_code": quotation.custom_shipping_service_code,
		},
	)
	return True


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


@frappe.whitelist()
def get_order_tracking(sales_order: str) -> dict:
	"""Customer-facing tracking for one of their own orders."""
	validate_document_access("Sales Order", sales_order)

	if not is_connector_installed():
		return {"has_tracking": False}

	shipment = frappe.get_all(
		"Shipping Request",
		filters={"ref_doctype": "Sales Order", "ref_docname": sales_order},
		fields=["name", "awb", "carrier", "status", "label_url"],
		order_by="creation desc",
		limit=1,
	)
	if not shipment or not shipment[0].awb:
		return {"has_tracking": False}

	request = shipment[0]
	events = frappe.get_all(
		"Shipping Tracking Event",
		filters={"parent": request.name, "parenttype": "Shipping Request"},
		fields=["timestamp", "status", "location", "message"],
		order_by="timestamp desc",
	)
	return {
		"has_tracking": True,
		"awb": request.awb,
		"carrier": request.carrier,
		"status": request.status,
		"events": events,
	}
