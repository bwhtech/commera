import frappe
from frappe import _

from commera.api.payments import VERSIONED_ADDRESS_FIELDS, get_checkout_payment_status


def validate(doc, method=None):
	"""A payment is placed with the addresses checkout start checked, so they stay as they are until it ends."""
	if doc.is_new() or not any(doc.has_value_changed(field) for field in VERSIONED_ADDRESS_FIELDS):
		return
	for quotation in get_open_carts(doc):
		# An unpaid session is released here, as a cart change releases it; the shopper starts checkout again.
		if get_checkout_payment_status(quotation):
			frappe.throw(
				_(
					"A payment is in progress for an order with this address. Finish or cancel it before you change the address."
				),
				title=_("Checkout In Progress"),
			)


def get_open_carts(address) -> list[str]:
	customers = [link.link_name for link in address.links if link.link_doctype == "Customer"]
	if not customers:
		return []
	return frappe.get_all(
		"Quotation",
		filters={"quotation_to": "Customer", "party_name": ("in", customers), "docstatus": 0},
		or_filters={"customer_address": address.name, "shipping_address_name": address.name},
		pluck="name",
	)
