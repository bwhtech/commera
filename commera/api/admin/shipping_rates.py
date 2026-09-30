# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""The Shipping Rates screen: the price bands on the store's one Shipping Rule, grouped by the delivery
option each band prices. bwh_shipping.pricing reads the bands; this module only edits them."""

import frappe
from frappe import _
from frappe.model.naming import append_number_if_name_exists
from frappe.utils.data import cstr

from commera.api.admin.delivery_options import (
	SERVICE_DOCTYPE,
	build_options,
	ensure_available,
	is_available,
)
from commera.api.admin.orders import get_reporting_currency
from commera.api.admin.settings import coerce_field_value, write_settings_fields

RULE_DOCTYPE = "Shipping Rule"
BAND_DOCTYPE = "Shipping Rule Condition"
SETTINGS_DOCTYPE = "Commera Settings"

NEW_RULE_LABEL = "Store Shipping"

# "Fixed" is left out on purpose: ShippingRule.validate deletes every band of a Fixed rule.
BASED_ON_CHOICES = ("Net Total", "Net Weight")
DEFAULT_BASED_ON = "Net Total"

BAND_FIELDS = ("name", "shipping_service", "from_value", "to_value", "shipping_amount", "free_shipping")
BAND_INPUT_FIELDS = ("from_value", "to_value", "shipping_amount", "free_shipping")

# bwh_shipping weighs a cart in kg whatever UOM each item is stored in (commera.api.shipping.to_kg).
WEIGHT_UOM = "kg"

FREIGHT_ACCOUNT_NAME = "Freight and Forwarding Charges"


def get_store_rule():
	"""The rule Commera Settings links to, or None before the first band is saved."""
	rule_name = frappe.db.get_single_value(SETTINGS_DOCTYPE, "shipping_rule")
	if not rule_name or not frappe.db.exists(RULE_DOCTYPE, rule_name):
		return None
	return frappe.get_doc(RULE_DOCTYPE, rule_name)


def build_screen() -> dict:
	"""Everything the Shipping Rates screen renders, in one read."""
	screen = {
		"available": False,
		"rule": None,
		"calculate_based_on": DEFAULT_BASED_ON,
		"currency": get_reporting_currency(),
		"weight_uom": WEIGHT_UOM,
		"bands": [],
		"delivery_options": [],
	}
	if not is_available():
		return screen

	frappe.has_permission(RULE_DOCTYPE, ptype="read", throw=True)

	rule = get_store_rule()
	screen["available"] = True
	screen["delivery_options"] = build_options()
	if rule:
		screen["rule"] = rule.name
		screen["calculate_based_on"] = rule.calculate_based_on
		screen["bands"] = [
			{fieldname: band.get(fieldname) for fieldname in BAND_FIELDS} for band in rule.conditions
		]
	return screen


def get_freight_account(company: str) -> str | None:
	return frappe.db.get_value(
		"Account", {"account_name": FREIGHT_ACCOUNT_NAME, "company": company, "is_group": 0}, "name"
	)


def get_cost_center(company: str) -> str | None:
	return frappe.get_cached_value("Company", company, "cost_center") or frappe.db.get_value(
		"Cost Center", {"company": company, "is_group": 0}, "name"
	)


def create_store_rule(calculate_based_on: str = DEFAULT_BASED_ON):
	"""A new selling rule on the store's company, linked on Commera Settings so pricing reads it."""
	company = frappe.db.get_single_value(SETTINGS_DOCTYPE, "company")
	if not company:
		frappe.throw(_("Set the company in Settings → General before adding shipping rates."))

	account = get_freight_account(company)
	if not account:
		frappe.throw(
			_("{0} has no {1} account for shipping charges to post to.").format(
				frappe.bold(company), frappe.bold(FREIGHT_ACCOUNT_NAME)
			)
		)

	rule = frappe.new_doc(RULE_DOCTYPE)
	rule.update(
		{
			"label": append_number_if_name_exists(RULE_DOCTYPE, NEW_RULE_LABEL, fieldname="label"),
			"shipping_rule_type": "Selling",
			"calculate_based_on": calculate_based_on,
			"company": company,
			"account": account,
			"cost_center": get_cost_center(company),
		}
	)
	rule.insert()

	write_settings_fields(("shipping_rule",), {"shipping_rule": rule.name})
	return rule


def parse_band(band: dict, shipping_service: str | None) -> dict:
	meta = frappe.get_meta(BAND_DOCTYPE)
	values = {
		fieldname: coerce_field_value(meta.get_field(fieldname).fieldtype, band.get(fieldname) or 0)
		for fieldname in BAND_INPUT_FIELDS
	}
	if values["shipping_amount"] < 0:
		frappe.throw(_("A band cannot charge less than zero."))
	# ERPNext applies the store rule as a tax row when no option is chosen, and that path ignores
	# free_shipping: a free band must carry no amount or the fallback bills it anyway.
	if values["free_shipping"]:
		values["shipping_amount"] = 0

	values["shipping_service"] = shipping_service
	return values


def get_kept_bands(rule, shipping_service: str | None) -> list[dict]:
	return [
		{fieldname: band.get(fieldname) for fieldname in BAND_FIELDS if fieldname != "name"}
		for band in rule.conditions
		if cstr(band.shipping_service) != cstr(shipping_service)
	]


@frappe.whitelist()
def get_shipping_rates() -> dict:
	"""The store rule's bands, the delivery options they price, and the currency they are in."""
	frappe.only_for("System Manager")

	return build_screen()


@frappe.whitelist(methods=["POST"])
def save_service_rates(shipping_service: str | None = None, bands: list | str | None = None) -> dict:
	"""Replace one delivery option's bands, leaving every other option's untouched; a blank
	`shipping_service` edits the bands that name no option. Returns the refreshed screen."""
	frappe.only_for("System Manager")
	ensure_available()

	shipping_service = cstr(shipping_service) or None
	if shipping_service and not frappe.db.exists(SERVICE_DOCTYPE, shipping_service):
		frappe.throw(_("Delivery option {0} not found").format(shipping_service), frappe.DoesNotExistError)

	rule = get_store_rule()
	if rule:
		frappe.has_permission(RULE_DOCTYPE, ptype="write", doc=rule, throw=True)
	else:
		rule = create_store_rule()

	new_bands = [parse_band(band, shipping_service) for band in frappe.parse_json(bands or [])]
	# Overlaps and a second open-ended band are refused by ShippingRule.validate, across the whole rule.
	rule.set("conditions", get_kept_bands(rule, shipping_service) + new_bands)
	rule.save()

	return build_screen()


@frappe.whitelist(methods=["POST"])
def set_rate_basis(calculate_based_on: str) -> dict:
	"""Price every band on order value or on weight. The band numbers are kept as they are.
	Returns the refreshed screen."""
	frappe.only_for("System Manager")
	ensure_available()

	if calculate_based_on not in BASED_ON_CHOICES:
		frappe.throw(_("Shipping rates are based on order value or weight."))

	rule = get_store_rule()
	if not rule:
		create_store_rule(calculate_based_on)
		return build_screen()

	frappe.has_permission(RULE_DOCTYPE, ptype="write", doc=rule, throw=True)
	rule.calculate_based_on = calculate_based_on
	rule.save()

	return build_screen()
