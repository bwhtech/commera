# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class CommeraOrderEvent(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		event: DF.Literal["order_placed", "order_paid"]
		sales_order: DF.Link
	# end: auto-generated types

	def autoname(self):
		# The name is the once-only lock: a second insert for the same order and event is a DuplicateEntryError.
		self.name = f"{self.sales_order}-{self.event}"
