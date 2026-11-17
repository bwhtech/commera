import frappe

try:
	from erpnext.stock.doctype.shipment.shipment import is_linked_to_party
except ImportError:

	def is_linked_to_party(doctype, name, party_type, party):
		return bool(
			frappe.db.exists(
				"Dynamic Link",
				{"parenttype": doctype, "parent": name, "link_doctype": party_type, "link_name": party},
			)
		)


# ERPNext moved its transaction mappers to a sibling `mapper` module; both layouts are in the wild.
try:
	from erpnext.selling.doctype.quotation.mapper import _make_sales_order
except ImportError:
	from erpnext.selling.doctype.quotation.quotation import _make_sales_order

try:
	from erpnext.selling.doctype.sales_order.mapper import make_delivery_note, make_sales_invoice
except ImportError:
	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note, make_sales_invoice


# ERPNext 16 keeps these checks on the document; the validator class exists from 17.
try:
	from erpnext.accounts.services.party_validation import PartyValidator
except ImportError:

	def PartyValidator(invoice):
		return invoice


try:
	from erpnext.accounts.services.payment_schedule import PaymentScheduleService

	def set_payment_schedule(doc):
		PaymentScheduleService(doc).set_payment_schedule()

except ImportError:

	def set_payment_schedule(doc):
		doc.set_payment_schedule()
