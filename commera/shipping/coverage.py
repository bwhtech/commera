"""Check whether the store Shipping Rule delivers to an address."""

import frappe


def ships_to_address(quotation, shipping_rule: str) -> bool:
	# As ERPNext's ShippingRule.apply: a document without a shipping address is not checked.
	address_name = quotation.get("shipping_address_name")
	if not address_name and (meta := getattr(quotation, "meta", None)):
		for fieldname in ("shipping_address",):
			field = meta.get_field(fieldname)
			if field and field.fieldtype == "Link" and quotation.get(fieldname):
				address_name = quotation.get(fieldname)
				break
	if not address_name:
		return True
	country = frappe.get_cached_value("Address", address_name, "country")
	return ships_to(shipping_rule, country)


def ships_to(shipping_rule: str, country: str | None) -> bool:
	# As ERPNext's validate_countries: a rule that lists no countries delivers everywhere.
	countries = [row.country for row in frappe.get_cached_doc("Shipping Rule", shipping_rule).countries]
	return not countries or country in countries


def get_store_shipping_rule() -> str | None:
	return frappe.get_cached_value("Commera Settings", "Commera Settings", "shipping_rule")
