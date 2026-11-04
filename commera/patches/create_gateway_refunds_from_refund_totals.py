import frappe
from bwh_payments_core.currency import get_minor_unit_exponent
from frappe.utils.data import flt

PAYMENT_REQUEST = "Gateway Payment Request"
REFUND = "Gateway Refund"


def execute():
	refunded_requests = frappe.get_all(
		PAYMENT_REQUEST,
		filters={"refund_amount": [">", 0]},
		fields=["name", "gateway", "currency_code", "refund_amount", "refund_id", "modified"],
	)
	if not refunded_requests:
		return

	with_ledger = set(
		frappe.get_all(
			REFUND,
			filters={"payment_request": ["in", [request.name for request in refunded_requests]]},
			pluck="payment_request",
			distinct=True,
		)
	)
	refund_logs = get_completed_refund_logs([request.name for request in refunded_requests])

	for request in refunded_requests:
		if request.name in with_ledger:
			continue
		for refund_id, amount in split_refunds(request, refund_logs.get(request.name, [])):
			insert_processed_refund(request, refund_id, amount)


def get_completed_refund_logs(payment_requests: list[str]) -> dict[str, list]:
	logs = {}
	for log in frappe.get_all(
		"Integration Request",
		filters={
			"reference_doctype": PAYMENT_REQUEST,
			"reference_docname": ["in", payment_requests],
			"integration_request_service": ["like", "% Refund"],
			"status": "Completed",
		},
		fields=["reference_docname", "integration_request_service", "data"],
		order_by="creation asc",
	):
		logs.setdefault(log.reference_docname, []).append(log)
	return logs


def split_refunds(request, logs: list) -> list[tuple[str | None, float]]:
	# develop appended each refund id in the order its request log completed.
	precision = get_minor_unit_exponent(request.currency_code)
	refund_ids = [refund_id for refund_id in (request.refund_id or "").split(",") if refund_id]
	amounts = [
		flt(frappe.parse_json(log.data).get("amount"), precision)
		for log in logs
		if log.integration_request_service == f"{request.gateway} Refund"
	]
	total = flt(request.refund_amount, precision)

	if amounts and len(amounts) == len(refund_ids) and flt(sum(amounts), precision) == total:
		return list(zip(refund_ids, amounts, strict=True))
	return [(refund_ids[0] if len(refund_ids) == 1 else None, total)]


def insert_processed_refund(request, refund_id: str | None, amount: float):
	# db_insert: refund_amount already holds this refund, and on_update would add it again.
	refund = frappe.get_doc(
		{
			"doctype": REFUND,
			"payment_request": request.name,
			"status": "Processed",
			"amount": amount,
			"currency": request.currency_code,
			"refund_id": refund_id,
			"owner": "Administrator",
			"modified_by": "Administrator",
			"creation": request.modified,
			"modified": request.modified,
		}
	)
	refund.set_new_name()
	refund.db_insert()
