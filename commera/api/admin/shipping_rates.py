# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""The Shipping Rules screen: the store's selling Shipping Rules, their bands, and which one checkout uses."""

import frappe
from frappe import _
from frappe.utils.data import cint, cstr

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

RULE_TYPE = "Selling"
CALCULATE_BASED_ON = "Net Total"

RULE_FIELDS = ("name", "label", "disabled")
BAND_FIELDS = ("name", "shipping_service", "from_value", "to_value", "shipping_amount", "free_shipping")
BAND_INPUT_FIELDS = ("from_value", "to_value", "shipping_amount", "free_shipping")

FREIGHT_ACCOUNT_NAME = "Freight and Forwarding Charges"


def get_store_company() -> str | None:
	return frappe.db.get_single_value(SETTINGS_DOCTYPE, "company")


def get_store_rule_name() -> str | None:
	return frappe.db.get_single_value(SETTINGS_DOCTYPE, "shipping_rule")


def build_rules(company: str) -> list[dict]:
	rules = frappe.get_all(
		RULE_DOCTYPE,
		filters={"company": company, "shipping_rule_type": RULE_TYPE},
		fields=list(RULE_FIELDS),
		order_by="label asc",
	)
	if not rules:
		return []

	bands_by_rule = {}
	for band in frappe.get_all(
		BAND_DOCTYPE,
		filters={"parenttype": RULE_DOCTYPE, "parent": ["in", [rule.name for rule in rules]]},
		fields=["parent", *BAND_FIELDS],
		order_by="idx asc",
	):
		parent = band.pop("parent")
		bands_by_rule.setdefault(parent, []).append(band)

	return [{**rule, "bands": bands_by_rule.get(rule.name, [])} for rule in rules]


def build_screen() -> dict:
	"""Everything the Shipping Rules screen renders, in one read."""
	screen = {
		"available": False,
		"store_rule": None,
		"currency": get_reporting_currency(),
		"rules": [],
		"delivery_options": [],
	}
	if not is_available():
		return screen

	frappe.has_permission(RULE_DOCTYPE, ptype="read", throw=True)

	company = get_store_company()
	screen["available"] = True
	screen["store_rule"] = get_store_rule_name()
	screen["delivery_options"] = build_options()
	screen["rules"] = build_rules(company) if company else []
	return screen


def get_freight_account(company: str) -> str | None:
	return frappe.db.get_value(
		"Account", {"account_name": FREIGHT_ACCOUNT_NAME, "company": company, "is_group": 0}, "name"
	)


def get_cost_center(company: str) -> str | None:
	return frappe.get_cached_value("Company", company, "cost_center") or frappe.db.get_value(
		"Cost Center", {"company": company, "is_group": 0}, "name"
	)


def new_store_rule(label: str):
	"""An unsaved selling rule on the store's company, posting to its freight account."""
	company = get_store_company()
	if not company:
		frappe.throw(_("Set the company in Settings → General before adding shipping rules."))

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
			"label": label,
			"shipping_rule_type": RULE_TYPE,
			"company": company,
			"account": account,
			"cost_center": get_cost_center(company),
		}
	)
	return rule


def get_listed_rule(name: str):
	"""The named rule, refused unless it is a selling rule of the store's company - the only ones listed."""
	rule = frappe.get_doc(RULE_DOCTYPE, cstr(name))
	if rule.shipping_rule_type != RULE_TYPE or rule.company != get_store_company():
		frappe.throw(
			_("{0} is not a selling shipping rule of the store's company.").format(frappe.bold(name))
		)
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


def parse_conditions(conditions) -> list[dict]:
	bands = frappe.parse_json(conditions or [])
	services = {cstr(band.get("shipping_service")) for band in bands} - {""}
	if services:
		found = frappe.get_all(SERVICE_DOCTYPE, filters={"name": ["in", list(services)]}, pluck="name")
		missing = sorted(services - set(found))
		if missing:
			frappe.throw(_("Delivery option {0} not found").format(missing[0]), frappe.DoesNotExistError)

	return [parse_band(band, cstr(band.get("shipping_service")) or None) for band in bands]


@frappe.whitelist()
def get_shipping_rules() -> dict:
	"""The store's selling rules with their bands, the one checkout uses, and the options a band can name."""
	frappe.only_for("System Manager")

	return build_screen()


@frappe.whitelist(methods=["POST"])
def save_shipping_rule(
	name: str | None = None,
	label: str | None = None,
	conditions: list | str | None = None,
	use_at_checkout: int = 0,
) -> dict:
	"""Create a rule (no `name`) or replace an existing rule's bands. Returns the refreshed screen."""
	frappe.only_for("System Manager")
	ensure_available()

	if name:
		if label:
			frappe.throw(_("A shipping rule's name cannot be changed."))
		rule = get_listed_rule(name)
		frappe.has_permission(RULE_DOCTYPE, ptype="write", doc=rule, throw=True)
	else:
		label = cstr(label).strip()
		if not label:
			frappe.throw(_("Name the shipping rule."))
		rule = new_store_rule(label)

	rule.calculate_based_on = CALCULATE_BASED_ON
	# Overlaps and a second open-ended band are refused by ShippingRule.validate.
	rule.set("conditions", parse_conditions(conditions))
	rule.save()

	if cint(use_at_checkout):
		write_settings_fields(("shipping_rule",), {"shipping_rule": rule.name})

	return build_screen()


@frappe.whitelist(methods=["POST"])
def delete_shipping_rule(name: str) -> dict:
	"""Delete a rule checkout does not use. Returns the refreshed screen."""
	frappe.only_for("System Manager")
	ensure_available()

	rule = get_listed_rule(name)
	if rule.name == get_store_rule_name():
		frappe.throw(
			_("Checkout uses {0}. Pick another rule for checkout before deleting it.").format(
				frappe.bold(rule.label)
			)
		)

	frappe.has_permission(RULE_DOCTYPE, ptype="delete", doc=rule, throw=True)
	frappe.delete_doc(RULE_DOCTYPE, rule.name)

	return build_screen()


@frappe.whitelist(methods=["POST"])
def set_store_rule(name: str) -> dict:
	"""Make checkout charge this rule's bands. Returns the refreshed screen."""
	frappe.only_for("System Manager")
	ensure_available()

	rule = get_listed_rule(name)
	frappe.has_permission(RULE_DOCTYPE, ptype="read", doc=rule, throw=True)
	write_settings_fields(("shipping_rule",), {"shipping_rule": rule.name})

	return build_screen()
