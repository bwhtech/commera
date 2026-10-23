import frappe
from frappe import _

from commera.core import is_shoppers_address


@frappe.whitelist()
def delete_user_address(address_id: str):
	"""Delete a user address by its ID."""
	if not address_id:
		frappe.throw(_("Address ID is required."))

	if not is_shoppers_address(address_id):
		frappe.throw(_("Cannot delete address"))

	address_doc = frappe.get_doc("Address", address_id)

	try:
		address_doc.flags.ignore_permissions = True
		address_doc.delete()
	except Exception:
		frappe.throw(_("Cannot delete address, it is in use"))
