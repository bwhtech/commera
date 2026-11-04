# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

from bwh_payments_core.connectors.razorpay.gateway import RazorpayGateway
from frappe.model.document import Document


class RazorpayGatewaySettings(Document, RazorpayGateway):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		cancelled_url: DF.Data | None
		currency: DF.Link | None
		enabled: DF.Check
		failure_url: DF.Data | None
		key_id: DF.Data
		key_secret: DF.Password
		send_razorpay_notifications: DF.Check
		success_url: DF.Data | None
		test_mode: DF.Check
		treat_authorised_as_paid: DF.Check
		webhook_secret: DF.Password | None
	# end: auto-generated types
