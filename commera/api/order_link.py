import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cstr

from commera.notifications import send_order_email
from commera.order_access import reset_order_access_key


# Guest lookup: the answer never says whether the order exists, and the link only goes to the order's own email.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=10, seconds=60 * 60)
def send_order_link(order_number: str, email: str) -> str:
	return email_order_link(order_number, email)


def email_order_link(order_number: str, email: str) -> str:
	order_number = cstr(order_number).strip()
	email = cstr(email).strip().lower()
	if order_number and email:
		contact_email = frappe.db.get_value("Sales Order", order_number, "contact_email")
		if contact_email and contact_email.strip().lower() == email:
			send_order_link_email(order_number, contact_email)
	return _("If that order number and email match an order, we have emailed you a link to it.")


def send_order_link_email(order_name: str, recipient: str):
	sales_order = frappe.get_doc("Sales Order", order_name)
	# A fresh key restarts the full-detail window and retires any older link that may have been shared.
	reset_order_access_key(sales_order)
	send_order_email("order_link", sales_order, [recipient])
