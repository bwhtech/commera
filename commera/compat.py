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
