"""Keep paid checkout addresses and shipping charges independent of live records."""

from html import unescape

import frappe
from frappe.utils import escape_html, strip_html

from commera.cart_prices import get_document_market
from commera.localization.address_countries import AddressCountries

PREFIX = "Accepted checkout: "
DETAIL_FIELDS = ("address_line1", "address_line2", "city", "state", "pincode", "country", "phone")
ADDRESS_FIELDS = ("customer_address", "shipping_address_name")


def accept_checkout(quotation):
	countries = AddressCountries.of(get_document_market(quotation))
	addresses = {}
	for field in ADDRESS_FIELDS:
		if name := quotation.get(field):
			address = frappe.get_doc("Address", name)
			addresses[field] = {
				"name": name,
				"country": address.country,
				"modified": str(address.modified),
				"details": {key: address.get(key) for key in DETAIL_FIELDS},
			}
	return {
		"addresses": addresses,
		"address_display": quotation.address_display,
		"shipping_address": quotation.shipping_address,
		"market": countries.market.handle,
		"market_countries": list(countries.market.countries),
		"shipping_rule": quotation.shipping_rule,
		"rule_countries": rule_countries(quotation.shipping_rule),
		"rule_config": rule_config(quotation.shipping_rule),
		"country_markets": {
			address["country"]: country_market(countries, address["country"])
			for address in addresses.values()
		},
	}


def validate_accepted_countries(quotation, accepted):
	countries = AddressCountries.of(get_document_market(quotation))
	for field, address in accepted["addresses"].items():
		if field == "shipping_address_name" and quotation.custom_is_store_pickup:
			continue
		countries.validate(address["country"])


def load_checkout(quotation):
	rows = frappe.get_all(
		"Comment",
		filters={"reference_doctype": "Quotation", "reference_name": quotation.name, "comment_type": "Info"},
		pluck="content",
		order_by="creation desc",
	)
	for content in rows:
		content = unescape(strip_html(content))
		if content.startswith(PREFIX):
			return frappe.parse_json(content[len(PREFIX) :])
	# Older sessions have only the quotation's rendered address snapshot.
	return accept_checkout(quotation)


def freeze_addresses(doc, accepted):
	# ERPNext renders linked addresses on every validate and checks current Customer links.
	# Keep the accepted text as transaction data; original links remain in the checkout comment.
	doc.flags.accepted_checkout = accepted
	clear_address_links(doc, accepted)


def note_checkout_changes(order, quotation, accepted):
	changes = []
	for field, old in accepted["addresses"].items():
		current = frappe.db.get_value("Address", old["name"], ["modified", *DETAIL_FIELDS], as_dict=True)
		linked = frappe.db.exists(
			"Dynamic Link",
			{
				"parenttype": "Address",
				"parent": old["name"],
				"link_doctype": "Customer",
				"link_name": quotation.party_name,
			},
		)
		differences = [
			f"{key}: {value or '(empty)'} → {current.get(key) or '(empty)'}"
			for key, value in old["details"].items()
			if current and current.get(key) != value
		]
		if not current:
			differences.append("Address deleted")
		if not linked:
			differences.append("Customer link removed")
		if differences:
			changes.append(f"{field} {old['name']}: " + ", ".join(differences))
	countries = AddressCountries.of(get_document_market(quotation))
	if sorted(accepted["market_countries"]) != sorted(countries.market.countries):
		changes.append(
			f"market {accepted['market']} countries: {accepted['market_countries']} → {list(countries.market.countries)}"
		)
	for country, old_market in accepted["country_markets"].items():
		new_market = country_market(countries, country)
		if new_market != old_market:
			changes.append(f"{country} market: {old_market} → {new_market}")
	for old in accepted["addresses"].values():
		if not countries.allows(frappe.get_cached_value("Country", old["country"], "code")):
			changes.append(f"the {countries.market.title} market no longer ships to {old['country']}")
	current_countries = rule_countries(accepted["shipping_rule"])
	if accepted["rule_countries"] != current_countries:
		changes.append(
			f"Shipping Rule {accepted['shipping_rule']} countries: {accepted['rule_countries']} → {current_countries}"
		)
	current_config = rule_config(accepted["shipping_rule"])
	if accepted["rule_config"] != current_config:
		changes.append(
			f"Shipping Rule {accepted['shipping_rule']} configuration: {accepted['rule_config']} → {current_config}"
		)
	if changes:
		order.add_comment(
			"Comment",
			escape_html(
				"Placed as paid with accepted addresses and totals. Check delivery: " + "; ".join(changes)
			),
		)


def rule_countries(name):
	if not name:
		return []
	return sorted(frappe.get_all("Shipping Rule Country", filters={"parent": name}, pluck="country"))


class PaidAddressMixin:
	def set_missing_lead_customer_details(self, for_validate=False):
		if accepted := self.flags.get("accepted_checkout"):
			clear_address_links(self, accepted)
			return
		super().set_missing_lead_customer_details(for_validate=for_validate)


def clear_address_links(doc, accepted):
	for field in ADDRESS_FIELDS:
		doc.set(field, None)
	for field in ("address_display", "shipping_address"):
		doc.set(field, accepted.get(field))


def paid_target(doctype, accepted):
	doc = frappe.new_doc(doctype)
	freeze_addresses(doc, accepted)
	return doc


def country_market(countries, country):
	return countries.markets.for_country(frappe.get_cached_value("Country", country, "code")).handle


def rule_config(name):
	if not name or not frappe.db.exists("Shipping Rule", name):
		return None
	rule = frappe.get_doc("Shipping Rule", name)
	return {
		"disabled": rule.disabled,
		"calculate_based_on": rule.calculate_based_on,
		"shipping_amount": rule.shipping_amount,
		"conditions": [
			{key: row.get(key) for key in ("from_value", "to_value", "shipping_amount")}
			for row in rule.conditions
		],
	}
