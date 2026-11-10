# Copyright (c) 2025, company@bwhstudios.com and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class LandingPageHeroBanner(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		banner_image: DF.AttachImage | None
		language: DF.Link | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		url: DF.Data | None
	# end: auto-generated types
	pass
