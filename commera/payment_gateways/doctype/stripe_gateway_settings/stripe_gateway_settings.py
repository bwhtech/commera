# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

from bwh_payments_core.connectors.stripe.gateway import StripeGateway
from frappe.model.document import Document


class StripeGatewaySettings(Document, StripeGateway):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		enabled: DF.Check
		failure_url: DF.Data | None
		mode: DF.Literal["Test", "Live"]
		private_key: DF.Password
		public_key: DF.Data
		success_url: DF.Data | None
		webhook_secret: DF.Password
	# end: auto-generated types
