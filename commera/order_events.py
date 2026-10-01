import frappe
from frappe.query_builder import DocType
from pypika.terms import ExistsCriterion


class OrderCancelRefused(frappe.ValidationError):
	pass


def fire_order_event(event: str, sales_order: str):
	"""Queue the apps' commera_<event> hooks for one order, once, after the caller's transaction commits."""
	# Checked first because a duplicate insert also msgprints a red "already exists" at whoever triggered it.
	if frappe.db.exists("Commera Order Event", {"sales_order": sales_order, "event": event}):
		return
	try:
		frappe.get_doc({"doctype": "Commera Order Event", "sales_order": sales_order, "event": event}).insert(
			ignore_permissions=True
		)
	except frappe.DuplicateEntryError:
		return

	frappe.enqueue(
		run_order_event_hooks,
		# Not `event=`: frappe.enqueue takes that keyword for itself and never hands it to the job.
		order_event=event,
		sales_order=sales_order,
		enqueue_after_commit=True,
	)


def run_order_event_hooks(order_event: str, sales_order: str):
	# Audited: only ever runs as a background job, so there is no shopper session to hijack.
	frappe.set_user("Administrator")  # nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
	for method in frappe.get_hooks(f"commera_{order_event}"):
		try:
			frappe.get_attr(method)(sales_order)
			# Per handler, not a savepoint: a handler may commit on its own, which would release the savepoint.
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title=f"commera_{order_event} hook failed: {method}",
				reference_doctype="Sales Order",
				reference_name=sales_order,
			)


def on_payment_entry_submit(doc, method=None):
	"""Fire order_paid for a cash-on-delivery order once it is fully billed and every invoice is settled.

	Gateway orders fire at checkout instead."""
	if doc.payment_type != "Receive":
		return

	invoice_names = [ref.reference_name for ref in doc.references if ref.reference_doctype == "Sales Invoice"]
	if not invoice_names:
		return

	sales_invoice_item = DocType("Sales Invoice Item")
	sales_order = DocType("Sales Order")
	unpaid_invoice = DocType("Sales Invoice").as_("unpaid_invoice")
	unpaid_invoice_item = DocType("Sales Invoice Item").as_("unpaid_invoice_item")
	unpaid_invoices = (
		frappe.qb.from_(unpaid_invoice_item)
		.join(unpaid_invoice)
		.on(unpaid_invoice.name == unpaid_invoice_item.parent)
		.select(unpaid_invoice_item.name)
		.where(
			(unpaid_invoice_item.sales_order == sales_order.name)
			& (unpaid_invoice.docstatus == 1)
			& (unpaid_invoice.outstanding_amount > 0)
		)
	)
	paid_orders = (
		frappe.qb.from_(sales_invoice_item)
		.join(sales_order)
		.on(sales_order.name == sales_invoice_item.sales_order)
		.select(sales_invoice_item.sales_order)
		.distinct()
		.where(
			sales_invoice_item.parent.isin(invoice_names)
			& (sales_order.custom_ecommerce_payment_mode == "COD")
			& (sales_order.per_billed >= 100)
			& ExistsCriterion(unpaid_invoices).negate()
		)
		.run(pluck=True)
	)
	for order_name in paid_orders:
		fire_order_event("order_paid", order_name)


def check_order_cancel_hooks(doc, method=None):
	"""Let an app refuse a webshop order's cancel; the first reason returned wins."""
	if not doc.get("custom_ecommerce_payment_mode"):
		return

	for hook in frappe.get_hooks("commera_before_order_cancel"):
		if reason := frappe.get_attr(hook)(doc.name):
			frappe.throw(reason, exc=OrderCancelRefused)
