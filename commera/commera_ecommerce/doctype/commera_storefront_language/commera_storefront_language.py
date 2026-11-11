# Copyright (c) 2026, hussain@buildwithhussain.com and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CommeraStorefrontLanguage(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		language: DF.Link
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		published: DF.Check
	# end: auto-generated types

	pass
