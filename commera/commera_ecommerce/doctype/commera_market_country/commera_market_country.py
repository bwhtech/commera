# Copyright (c) 2026, hussain@buildwithhussain.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

UNIQUE_COUNTRY = "unique_market_country"


class CommeraMarketCountry(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		country: DF.Link
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	def show_unique_validation_message(self, e):
		"""Another market claimed this country after validate() read the countries."""
		from commera.commera_ecommerce.doctype.commera_market.commera_market import throw_country_taken

		market = frappe.db.get_value(
			self.doctype, {"country": self.country, "parent": ["!=", self.parent]}, "parent"
		)
		throw_country_taken(self.country, market, frappe.UniqueValidationError)


def on_doctype_update():
	frappe.db.add_unique("Commera Market Country", ["country"], constraint_name=UNIQUE_COUNTRY)
