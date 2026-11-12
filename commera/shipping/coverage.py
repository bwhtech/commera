"""Where the store's Shipping Rule delivers, and which account it may post to.

ERPNext's ShippingRule.apply throws for a shipping address outside the rule's countries. A cart leaves the rule
off instead, and checkout refuses payment, so the shopper sees that no delivery is available there.
"""

import frappe
from frappe import _


def ships_to_address(quotation, shipping_rule: str) -> bool:
	# As ERPNext's ShippingRule.apply: a document without a shipping address is not checked.
	address = quotation.get_shipping_address()
	return not address or ships_to(shipping_rule, address.get("country"))


def ships_to(shipping_rule: str, country: str | None) -> bool:
	# As ERPNext's validate_countries: a rule that lists no countries delivers everywhere.
	countries = [row.country for row in frappe.get_cached_doc("Shipping Rule", shipping_rule).countries]
	return not countries or country in countries


def validate_charge_account(
	charge_account: str | None, shipping_rule: str | None, rule_account: str | None = None
):
	"""ERPNext re-applies a Shipping Rule to the last Actual row on its account at every recalculation, so a
	cash on delivery fee or app fee on that account would silently become the shipping amount."""
	if not (charge_account and shipping_rule):
		return
	rule_account = rule_account or frappe.db.get_value("Shipping Rule", shipping_rule, "account")
	if charge_account == rule_account:
		frappe.throw(
			_(
				"The Charge Account Head {0} is also the account of the store's Shipping Rule {1}. The Shipping"
				" Rule overwrites every charge on its account, so set a different account for one of them."
			).format(frappe.bold(charge_account), frappe.bold(shipping_rule)),
			title=_("Shared Charge Account"),
		)


def get_store_shipping_rule() -> str | None:
	return frappe.get_cached_value("Commera Settings", "Commera Settings", "shipping_rule")
