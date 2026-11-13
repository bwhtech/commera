"""Place a paid cart as accepted at checkout start: the cart save there rendered its address text and charges,
and the cart lock keeps them. Live records that changed since only produce a staff note."""

import frappe
from erpnext.accounts.party import render_address
from frappe import _
from frappe.utils import escape_html, flt, strip_html

from commera.api.shipping import CART_CHARGE_FIELD, get_cart_charge_kind
from commera.cart_prices import get_document_market
from commera.localization.address_countries import AddressCountries

ADDRESS_TEXT = {"customer_address": "address_display", "shipping_address_name": "shipping_address"}


def keep_accepted_checkout(quotation) -> list[str]:
	"""Keep the paid cart's addresses and shipping charge through submission. Returns what changed."""
	changes = get_address_changes(quotation)
	for field in ADDRESS_TEXT:
		# A deleted Address fails link validation; its accepted text stays.
		if (name := quotation.get(field)) and not frappe.db.exists("Address", name):
			quotation.set(field, None)
	if reason := get_shipping_rule_change(quotation):
		release_shipping_rule(quotation)
		changes.append(reason)
	keep_accepted_addresses(quotation, quotation)
	return changes


def keep_accepted_addresses(doc, source):
	"""ERPNext refills and renders the address links on every validate; keep the values of `source`."""
	fields = [*ADDRESS_TEXT, *ADDRESS_TEXT.values()]
	doc.flags.accepted_addresses = {field: source.get(field) for field in fields}


def restore_accepted_addresses(doc, method=None):
	doc.update(doc.flags.get("accepted_addresses") or {})


def get_shipping_rule_change(quotation) -> str | None:
	"""Why ERPNext would refuse or reprice the accepted shipping charge on submit, if it would."""
	name = quotation.shipping_rule
	if not name:
		return None
	if not frappe.db.exists("Shipping Rule", name):
		return _("Shipping Rule {0} was deleted").format(name)
	rule = frappe.get_doc("Shipping Rule", name)
	address = quotation.get_shipping_address()
	countries = [row.country for row in rule.countries]
	if address and countries and address.get("country") not in countries:
		return _("Shipping Rule {0} no longer covers {1}").format(name, address.get("country"))
	trial = frappe.copy_doc(quotation, ignore_no_copy=True)
	rule.apply(trial)
	if get_charge_amounts(trial) != get_charge_amounts(quotation):
		return _("Shipping Rule {0} now charges a different amount").format(name)
	return None


def get_charge_amounts(doc) -> list[float]:
	return [flt(row.tax_amount, row.precision("tax_amount")) for row in doc.taxes]


def release_shipping_rule(quotation):
	"""Keep the accepted shipping row, marked so order charge lines still show it as shipping."""
	for row in quotation.taxes:
		if get_cart_charge_kind(row, quotation) == "shipping_rule":
			row.set(CART_CHARGE_FIELD, "shipping_rule")
	quotation.shipping_rule = None


def get_address_changes(quotation) -> list[str]:
	try:
		return list(dict.fromkeys(read_address_changes(quotation)))
	except Exception:
		frappe.log_error(
			"Paid order address check failed", reference_doctype="Quotation", reference_name=quotation.name
		)
		return []


def read_address_changes(quotation):
	countries = AddressCountries.of(get_document_market(quotation))
	for field, text_field in ADDRESS_TEXT.items():
		name = quotation.get(field)
		if not name or (field == "shipping_address_name" and quotation.custom_is_store_pickup):
			continue
		address = frappe.db.get_value("Address", name, "country")
		if not address:
			yield _("Address {0} was deleted").format(name)
			continue
		if normalize(render_address(name, check_permissions=False)) != normalize(quotation.get(text_field)):
			yield _("Address {0} was edited").format(name)
		if not is_linked(name, quotation):
			yield _("Address {0} is no longer linked to {1}").format(name, quotation.party_name)
		if not countries.allows(frappe.get_cached_value("Country", address, "code")):
			yield _("the {0} market no longer ships to {1}").format(_(countries.market.title), _(address))


def is_linked(address: str, quotation) -> bool:
	return bool(
		frappe.db.exists(
			"Dynamic Link",
			{
				"parenttype": "Address",
				"parent": address,
				"link_doctype": quotation.quotation_to,
				"link_name": quotation.party_name,
			},
		)
	)


def normalize(text: str | None) -> str:
	return " ".join(strip_html(text or "").split())


def note_checkout_changes(order, changes: list[str]):
	if not changes:
		return
	note = _("Placed as paid with the accepted addresses and totals. Check delivery: {0}.")
	try:
		order.add_comment("Comment", escape_html(note.format("; ".join(changes))))
	except Exception:
		frappe.log_error(
			"Paid order change note failed", reference_doctype="Sales Order", reference_name=order.name
		)
