# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from bwh_payments_core.connectors.telr.gateway import TelrGateway
from frappe.model.document import Document


class TelrGatewaySettings(Document, TelrGateway):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		auth_key: DF.Password
		authorised_url: DF.Data | None
		cancelled_url: DF.Data | None
		currency: DF.Link | None
		declined_url: DF.Data | None
		enabled: DF.Check
		remote_auth_key: DF.Password | None
		store_id: DF.Data
		test_mode: DF.Check
		treat_authorised_as_paid: DF.Check
	# end: auto-generated types

	@frappe.whitelist()
	def get_account_information(self):
		return super().get_account_information()
