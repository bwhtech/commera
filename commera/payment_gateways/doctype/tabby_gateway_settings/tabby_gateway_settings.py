# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

from bwh_payments_core.connectors.tabby.gateway import TabbyGateway
from frappe.model.document import Document


class TabbyGatewaySettings(Document, TabbyGateway):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		cancelled_url: DF.Data | None
		currency: DF.Link | None
		enabled: DF.Check
		failure_url: DF.Data | None
		key_secret: DF.Password
		merchant_code: DF.Data
		success_url: DF.Data | None
		webhook_ips: DF.SmallText | None
		webhook_secret: DF.Password
	# end: auto-generated types
