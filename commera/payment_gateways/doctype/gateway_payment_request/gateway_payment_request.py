# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from bwh_payments_core.engine.payment_request import GatewayPaymentRequestMixin
from frappe.model.document import Document

RETURN_ENDPOINT = "/api/method/commera.payment_gateways.api.return_from_gateway"


class GatewayPaymentRequest(Document, GatewayPaymentRequestMixin):
	return_endpoint = RETURN_ENDPOINT

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Currency
		cancel_url: DF.Data | None
		company: DF.Link | None
		currency_code: DF.Link
		customer_address: DF.Link | None
		customer_email: DF.Data | None
		customer_forenames: DF.Data | None
		customer_phone: DF.Data | None
		customer_ref: DF.Link | None
		customer_surname: DF.Data | None
		erpnext_payment_request: DF.Link | None
		failure_url: DF.Data | None
		gateway: DF.Link
		gateway_transaction_ref: DF.Data | None
		last_webhook_event_id: DF.Data | None
		order_ref: DF.Data | None
		order_url: DF.SmallText | None
		ref_docname: DF.DynamicLink
		ref_doctype: DF.Link
		refund_amount: DF.Currency
		refund_id: DF.SmallText | None
		refund_payment_entries: DF.SmallText | None
		status: DF.Literal[
			"Pending", "Paid", "Not Paid", "Cancelled", "Expired", "Partially Refunded", "Refunded"
		]
		success_url: DF.Data | None
	# end: auto-generated types

	@frappe.whitelist()
	def sync_status(self):
		return super().sync_status()

	@frappe.whitelist()
	def sync_refunds(self):
		return super().sync_refunds()
