import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cstr, escape_html

from commera.order_access import get_order_link, reset_order_access_key


# Guest lookup: the answer never says whether the order exists, and the link only goes to the order's own email.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=10, seconds=60 * 60)
def send_order_link(order_number: str, email: str) -> str:
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
	order_link = escape_html(get_order_link(sales_order))
	frappe.sendmail(
		recipients=[recipient],
		subject=_("Your order {0}").format(order_name),
		message=_("Open your order {0}: {1}").format(order_name, f'<a href="{order_link}">{order_link}</a>'),
		reference_doctype="Sales Order",
		reference_name=order_name,
	)
