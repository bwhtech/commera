# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CommeraEmail(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		email: DF.Literal[
			"order_confirmation",
			"order_cancelled",
			"back_in_stock",
			"order_link",
			"sign_in_code",
			"order_shipped",
			"order_delivered",
			"order_refunded",
			"order_returned",
			"payment_failed",
		]
		email_template: DF.Link | None
		enabled: DF.Check
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		template: DF.Data | None
	# end: auto-generated types

	pass
