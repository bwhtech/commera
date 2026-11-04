# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

from bwh_payments_core.engine.refund import GatewayRefundMixin
from frappe.model.document import Document


class GatewayRefund(Document, GatewayRefundMixin):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Currency
		currency: DF.Link | None
		error: DF.SmallText | None
		last_webhook_event_id: DF.Data | None
		payment_entry: DF.Data | None
		payment_request: DF.Link
		reference: DF.Data | None
		refund_id: DF.Data | None
		status: DF.Literal["Pending", "Processed", "Failed"]
	# end: auto-generated types
