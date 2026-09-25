import frappe
from erpnext.accounts.utils import unlink_ref_doc_from_payment_entries
from frappe import _
from frappe.utils import flt

from commera.api.payments import system_user_session
from commera.utils import update_sales_order_ecommerce_status, validate_document_access


@frappe.whitelist()
def cancel_order(order_id: str):
	order_doc = frappe.get_doc("Sales Order", order_id, for_update=True)
	validate_can_cancel(order_doc)

	try:
		refund = None
		if order_doc.custom_ecommerce_payment_mode != "COD":
			refund = get_refund_plan(order_id)

		if cancel_order_invoices(order_id):
			order_doc.reload()

		order_doc.flags.ignore_permissions = True
		if order_doc.docstatus == 1:
			order_doc.cancel()
		elif order_doc.docstatus == 0:
			order_doc.submit()
			order_doc.reload()
			order_doc.cancel()
		# The on_cancel hook only enqueues this, so the page would reload onto the old status.
		update_sales_order_ecommerce_status(order_id)

		if refund:
			submit_refund_payment_entry(order_id, *refund)
	except Exception:
		frappe.log_error(
			title="Order cancellation failed", reference_doctype="Sales Order", reference_name=order_id
		)
		raise


def cancel_order_invoices(order_id: str):
	invoice_names = frappe.get_all(
		"Sales Invoice Item",
		filters={"sales_order": order_id, "docstatus": 1},
		pluck="parent",
		distinct=True,
	)
	with system_user_session():
		for invoice_name in invoice_names:
			sales_invoice = frappe.get_doc("Sales Invoice", invoice_name)
			unlink_ref_doc_from_payment_entries(sales_invoice)
			sales_invoice.flags.ignore_permissions = True
			sales_invoice.cancel()

	return invoice_names


def resolve_refund_amount(refundable_amount: float, amount: float | None) -> float:
	"""Clamp a requested refund to what the order still owes back. Only `None` means "the balance":
	a non-numeric post coerces to 0, and `or` would read that as unspecified and pay out the max."""
	precision = frappe.get_precision("Payment Entry", "paid_amount")
	refundable_amount = flt(refundable_amount, precision)
	refund_amount = refundable_amount if amount is None else flt(amount, precision)

	if refund_amount <= 0 or refund_amount > refundable_amount:
		frappe.throw(_("Refund amount must be between 0 and {0}.").format(refundable_amount))

	return refund_amount


def make_refund_payment_entry(order_id: str, amount: float | None = None) -> str:
	"""Submit the Payment Entry that reverses a paid order. Callers must authorize access first."""
	# Without this lock two concurrent refunds both see the pre-refund balance and both pay out.
	sales_order = frappe.get_doc("Sales Order", order_id)
	sales_order.lock()
	try:
		return build_refund_payment_entry(order_id, amount)
	finally:
		# The lock is a file, so a rollback does not clear it: without this a refused refund locks
		# the order for good.
		sales_order.unlock()


def build_refund_payment_entry(order_id: str, amount: float | None = None) -> str:
	"""The refund itself. Call make_refund_payment_entry, which holds the lock around this."""
	return submit_refund_payment_entry(order_id, *get_refund_plan(order_id, amount))


def get_refund_plan(order_id: str, amount: float | None = None) -> tuple:
	refund_status = get_refund_status(order_id)
	if not refund_status.get("can_refund"):
		frappe.throw(_("This order cannot be refunded."))

	refund_amount = resolve_refund_amount(refund_status["refundable_amount"], amount)

	payments = get_order_payments(order_id)
	if not payments:
		frappe.throw(_("No Payment Entry found for this Sales Order."))

	payment_entry_doc = frappe.get_doc("Payment Entry", payments[0].name)

	# ponytail: single-currency refunds only, revisit when a gateway settles in another currency.
	# The reversal swaps the accounts, so equal currencies are what makes received == paid below.
	if payment_entry_doc.paid_from_account_currency != payment_entry_doc.paid_to_account_currency:
		frappe.throw(_("This payment crossed currencies; refund it from the accounts desk instead."))

	return payment_entry_doc, refund_amount


def submit_refund_payment_entry(order_id: str, payment_entry_doc, refund_amount: float) -> str:
	with system_user_session():
		new_payment_entry = frappe.get_doc(
			{
				"doctype": "Payment Entry",
				"payment_type": "Pay",
				"mode_of_payment": payment_entry_doc.mode_of_payment,
				"party_type": payment_entry_doc.party_type,
				"party": payment_entry_doc.party,
				"company": payment_entry_doc.company,
				"paid_from": payment_entry_doc.paid_to,
				"paid_to": payment_entry_doc.paid_from,
				"paid_amount": refund_amount,
				# validate_mandatory() runs before set_amounts(), so set_received_amount() never gets
				# to derive this and the entry cannot insert. Equal currencies make the two the same.
				"received_amount": refund_amount,
				"reference_no": payment_entry_doc.reference_no,
				"reference_date": frappe.utils.nowdate(),
				"remarks": f"Refund for Sales Order {order_id}",
			}
		)
		new_payment_entry.insert(ignore_permissions=True)
		new_payment_entry.submit()

	return new_payment_entry.name


@frappe.whitelist()
def create_refund_payment_entry(order_id: str, amount: float | None = None) -> str:
	"""Refund an order from the Sales Order form. Staff only."""
	# The Desk dialog's bound is browser-side only; make_refund_payment_entry clamps for real.
	frappe.has_permission("Sales Order", ptype="write", doc=order_id, throw=True)

	return make_refund_payment_entry(order_id, amount)


def validate_can_cancel(order_doc):
	if order_doc.docstatus > 1:
		frappe.throw(_("Order already cancelled!"))

	if order_doc.status == "To Bill":
		frappe.throw(_("Order already shipped!"))

	if order_doc.status == "Completed":
		frappe.throw(_("Order already delivered!"))

	if frappe.db.exists("Delivery Note Item", {"against_sales_order": order_doc.name, "docstatus": ["<", 2]}):
		frappe.throw(_("This order is already being prepared for shipment."))

	if order_doc.owner != frappe.session.user:
		frappe.throw(_("Action not allowed"))


def get_order_payments(order_id: str | int) -> list:
	"""Submitted captures for one order, oldest first. Checkout books the payment against the Sales Invoice
	raised from the order, while a Desk advance references the Sales Order itself - both count."""
	invoice_names = set(
		frappe.get_all(
			"Sales Invoice Item",
			filters={"sales_order": order_id, "docstatus": 1},
			pluck="parent",
		)
	)

	reference_filters = [{"reference_doctype": "Sales Order", "reference_name": order_id}]
	if invoice_names:
		reference_filters.append(
			{"reference_doctype": "Sales Invoice", "reference_name": ["in", sorted(invoice_names)]}
		)

	payment_entry_names = set()
	for filters in reference_filters:
		payment_entry_names.update(frappe.get_all("Payment Entry Reference", filters=filters, pluck="parent"))

	if not payment_entry_names:
		return []

	return frappe.get_all(
		"Payment Entry",
		filters={
			"name": ["in", sorted(payment_entry_names)],
			"payment_type": "Receive",
			"docstatus": 1,
		},
		fields=["name", "paid_amount", "reference_no", "mode_of_payment", "party_type", "party", "company"],
		# Ordered so a second gateway attempt cannot change which entry a refund is modelled on.
		order_by="creation asc",
	)


def get_refund_refusal(order, reason: str, total_refunded: float = 0.0) -> dict:
	"""Carries the same keys as a refundable order, so callers never branch on which shape they got."""
	return {
		"can_refund": False,
		"reason": reason,
		"currency": order.currency,
		"only_charges": False,
		"amount_refunded": total_refunded,
		"refundable_amount": 0.0,
	}


def get_refund_status(order_id: str | int) -> dict:
	"""Refund math for one order. Callers must authorize access first."""
	order = frappe.get_doc("Sales Order", order_id)
	if order.custom_ecommerce_payment_mode == "COD":
		return get_refund_refusal(order, _("This order is paid on delivery, so there is nothing to refund."))

	payments = get_order_payments(order_id)
	if not payments:
		return get_refund_refusal(order, _("No payment has been captured for this order yet."))

	capture = payments[0]
	refund_payment_entries = frappe.get_all(
		"Payment Entry",
		filters={
			"payment_type": "Pay",
			"reference_no": capture.reference_no,
			# Gateways reuse reference numbers across parties; an unscoped match pulls in another's refund.
			"party_type": capture.party_type,
			"party": capture.party,
			"company": capture.company,
			"docstatus": 1,
		},
		fields=["paid_amount"],
	)

	total_refunded = sum(flt(pe.paid_amount) for pe in refund_payment_entries)

	if total_refunded >= order.rounded_total:
		return get_refund_refusal(order, _("This order has already been refunded in full."), total_refunded)

	only_charges = total_refunded >= order.net_total
	refundable_amount = order.rounded_total - total_refunded

	return {
		"can_refund": True,
		"reason": None,
		"currency": order.currency,
		"only_charges": only_charges,
		"amount_refunded": total_refunded,
		"refundable_amount": refundable_amount,
	}


@frappe.whitelist()
def get_sales_order_refund_status(order_id: str):
	validate_document_access("Sales Order", order_id)
	return get_refund_status(order_id)
