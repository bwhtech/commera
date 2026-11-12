import frappe

from commera.shipping.coverage import get_store_shipping_rule, validate_charge_account


def validate(doc, method=None):
	if doc.name == get_store_shipping_rule():
		charge_account = frappe.db.get_single_value("Commera Settings", "charge_account_head")
		validate_charge_account(charge_account, doc.name, rule_account=doc.account)
