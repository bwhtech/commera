# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""The Shipping rates screen: ERPNext Shipping Rules and their price bands, edited without Desk.
A delivery option points at one of these, and bwh_shipping.pricing prices the cart from its bands."""

from itertools import pairwise

import frappe
from frappe import _
from frappe.utils.data import cint, cstr, flt

from commera.api.admin.docfields import search_link_options

RULE_DOCTYPE = "Shipping Rule"
BAND_DOCTYPE = "Shipping Rule Condition"
SETTINGS_DOCTYPE = "Commera Settings"
SERVICE_DOCTYPE = "Shipping Service"

LINK_OPTIONS_PATH = "shipping_rules.get_link_options"

# Fixed is left out on purpose: it carries no bands, and bwh_shipping only prices a cart from a band.
BASED_ON_CHOICES = ("Net Total", "Net Weight")

RULE_FIELDS = ("name", "label", "disabled", "calculate_based_on", "company", "account", "cost_center")
BAND_FIELDS = ("parent", "from_value", "to_value", "shipping_amount")

# Stock charts name the account "Freight and Forwarding Charges" and type it Chargeable - alongside
# Marketing and Miscellaneous, so the type alone would pick an unrelated account.
FREIGHT_ACCOUNT_NAMES = ("%freight%", "%shipping%")


def get_store_company() -> str:
	company = frappe.db.get_single_value(SETTINGS_DOCTYPE, "company")
	if not company:
		frappe.throw(_("Set the company in Settings → General before adding shipping rates."))
	return company


def get_default_account(company: str) -> str | None:
	"""The company's freight expense account, or None when none is named like one - the owner then picks."""
	for account_name in FREIGHT_ACCOUNT_NAMES:
		account = frappe.db.get_value(
			"Account",
			{
				"company": company,
				"is_group": 0,
				"disabled": 0,
				"root_type": "Expense",
				"account_name": ("like", account_name),
			},
			"name",
			order_by="name asc",
		)
		if account:
			return account
	return None


def get_rules(name: str | None = None) -> list[dict]:
	"""Every selling rule, or the one named, its bands in the order pricing reads them."""
	filters = {"shipping_rule_type": "Selling"}
	if name:
		filters["name"] = name

	rules = frappe.get_all(
		RULE_DOCTYPE,
		filters=filters,
		fields=list(RULE_FIELDS),
		order_by="label asc",
	)
	if not rules:
		return []

	bands_by_rule = {rule.name: [] for rule in rules}
	for band in frappe.get_all(
		BAND_DOCTYPE,
		filters={"parenttype": RULE_DOCTYPE, "parent": ("in", list(bands_by_rule))},
		fields=list(BAND_FIELDS),
		order_by="idx asc",
	):
		bands_by_rule[band.pop("parent")].append(band)

	used_by = get_linking_options()
	store_default = frappe.db.get_single_value(SETTINGS_DOCTYPE, "shipping_rule")
	for rule in rules:
		rule["bands"] = bands_by_rule[rule.name]
		rule["used_by"] = used_by.get(rule.name, [])
		rule["is_store_default"] = rule.name == store_default
	return rules


def get_linking_options() -> dict[str, list[str]]:
	if not frappe.db.exists("DocType", SERVICE_DOCTYPE):
		return {}

	used_by = {}
	for option in frappe.get_all(
		SERVICE_DOCTYPE,
		filters={"shipping_rule": ("is", "set")},
		fields=["title", "shipping_rule"],
		order_by="title asc",
	):
		used_by.setdefault(option.shipping_rule, []).append(option.title)
	return used_by


def build_screen() -> dict:
	frappe.has_permission(RULE_DOCTYPE, ptype="read", throw=True)

	company = frappe.db.get_single_value(SETTINGS_DOCTYPE, "company")
	return {
		"rules": get_rules(),
		"company": company,
		# Offered, not forced: the dialog prefills it, and a store without one is asked to pick.
		"default_account": get_default_account(company) if company else None,
		"link_options_path": LINK_OPTIONS_PATH,
	}


def parse_bands(bands: list | str | None) -> list[dict]:
	"""The bands as numbers, lowest first, so pricing's first-match walk reads them in order."""
	parsed = [
		{
			"from_value": flt(band.get("from_value")),
			"to_value": flt(band.get("to_value")),
			"shipping_amount": flt(band.get("shipping_amount")),
		}
		for band in frappe.parse_json(bands or [])
	]
	return sorted(parsed, key=lambda band: band["from_value"])


def validate_bands(bands: list[dict]):
	"""What ERPNext's own validate does not refuse, or refuses unreadably. From < to and a second
	open-ended band are left to ShippingRule.validate."""
	if not bands:
		frappe.throw(_("Add at least one price band."))

	for band in bands:
		if band["shipping_amount"] < 0:
			frappe.throw(_("A band cannot charge less than zero."))

	# ERPNext refuses overlaps too, but its message is only the two ranges, with no reason given.
	# Touching edges (0-999, then 999 up) are allowed, as ERPNext allows them; the lower band wins.
	for lower, upper in pairwise(bands):
		if lower["to_value"] and upper["from_value"] < lower["to_value"]:
			frappe.throw(
				_("Bands overlap: {0}-{1} and {2}-{3}. Start each band where the one before it ends.").format(
					lower["from_value"], lower["to_value"], upper["from_value"], upper["to_value"] or "…"
				)
			)

	# ERPNext checks an open-ended band's overlap as the single point at its From value, so an
	# open band starting below another band passes there - and pricing, walking bands in order,
	# would then charge the open band's amount to carts the higher band was meant to price.
	highest_from = max(band["from_value"] for band in bands)
	for band in bands:
		if not band["to_value"] and band["from_value"] < highest_from:
			frappe.throw(_("Only the highest band can be open-ended (no To value)."))


def set_new_rule_defaults(rule, account: str | None):
	company = get_store_company()
	rule.shipping_rule_type = "Selling"
	rule.company = company
	rule.cost_center = frappe.get_cached_value("Company", company, "cost_center")
	rule.account = account or get_default_account(company)
	if not rule.account:
		frappe.throw(
			_("{0} has no freight expense account. Pick the account shipping charges should post to.").format(
				frappe.bold(company)
			)
		)


@frappe.whitelist()
def get_shipping_rules() -> dict:
	"""Every shipping rule with its bands, and what a new one would default to."""
	frappe.only_for("System Manager")

	return build_screen()


@frappe.whitelist()
def get_shipping_rule(name: str) -> dict:
	frappe.only_for("System Manager")
	frappe.has_permission(RULE_DOCTYPE, ptype="read", doc=cstr(name), throw=True)

	rules = get_rules(cstr(name))
	if not rules:
		frappe.throw(_("Shipping rule {0} not found").format(cstr(name)), frappe.DoesNotExistError)
	return rules[0]


@frappe.whitelist(methods=["POST"])
def save_shipping_rule(
	name: str | None = None,
	label: str | None = None,
	calculate_based_on: str = "Net Total",
	bands: list | str | None = None,
	account: str | None = None,
	disabled: int | str = 0,
) -> dict:
	"""Create a rule, or replace an existing rule's bands; a blank `name` creates. Returns the refreshed
	screen. The label is fixed on edit: it is the rule's name, and delivery options link to it by name."""
	frappe.only_for("System Manager")

	if calculate_based_on not in BASED_ON_CHOICES:
		frappe.throw(_("A shipping rate is priced on cart value or weight."))

	parsed_bands = parse_bands(bands)
	validate_bands(parsed_bands)

	if name:
		rule = frappe.get_doc(RULE_DOCTYPE, cstr(name))
		if account:
			rule.account = account
	else:
		rule = frappe.new_doc(RULE_DOCTYPE)
		rule.label = cstr(label).strip()
		set_new_rule_defaults(rule, account)

	rule.calculate_based_on = calculate_based_on
	rule.disabled = cint(disabled)
	rule.set("conditions", parsed_bands)
	rule.save()

	return build_screen()


@frappe.whitelist(methods=["POST"])
def delete_shipping_rule(name: str) -> dict:
	"""Remove a rule no delivery option and no store setting still prices from. Returns the refreshed screen."""
	frappe.only_for("System Manager")
	name = cstr(name)

	used_by = get_linking_options().get(name)
	if used_by:
		frappe.throw(
			_("{0} still prices {1}. Point those delivery options at another rule first.").format(
				frappe.bold(name), ", ".join(used_by)
			),
			frappe.LinkExistsError,
		)
	if frappe.db.get_single_value(SETTINGS_DOCTYPE, "shipping_rule") == name:
		frappe.throw(
			_("{0} is the store's default shipping rule. Choose another default in Settings first.").format(
				frappe.bold(name)
			),
			frappe.LinkExistsError,
		)

	frappe.delete_doc(RULE_DOCTYPE, name)
	return build_screen()


@frappe.whitelist()
def get_link_options(doctype: str, search_text: str | None = None):
	"""Options for the rule editor's account and cost center pickers, limited to the store's company."""
	frappe.only_for("System Manager")

	if doctype not in ("Account", "Cost Center"):
		frappe.throw(_("A shipping rule cannot link to {0}.").format(doctype))

	return search_link_options(doctype, search_text, filters={"company": get_store_company(), "is_group": 0})
