import frappe
from erpnext.accounts.party import find_party_account
from erpnext.accounts.services.party_validation import PartyValidator


def get_invoice_currency_error(company: str, currency: str, customer: str | None = None) -> str | None:
	"""Why ERPNext would refuse a Sales Invoice in `currency`, or None if it accepts one.

	A paid cart is invoiced right after the gateway captures it, so checkout asks before it opens a session.
	These are the party checks Sales Invoice runs on save, on a draft that is never saved. No `customer`
	stands for a new one, on the company's default receivable account.
	"""
	invoice = frappe.new_doc("Sales Invoice")
	invoice.update(
		{
			"company": company,
			"customer": customer,
			"currency": currency,
			"debit_to": find_party_account("Customer", customer, company),
		}
	)
	validator = PartyValidator(invoice)
	muted = frappe.flags.mute_messages
	# Muted, so the refusal is ours to word and ERPNext's message does not reach the shopper.
	frappe.flags.mute_messages = True
	try:
		validator.validate_currency()
		validator.validate_party_account_currency()
	except frappe.ValidationError as error:
		return str(error)
	finally:
		frappe.flags.mute_messages = muted
	return None
