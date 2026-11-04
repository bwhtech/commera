# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class CommeraWishlistItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		product: DF.Link
		user: DF.Link
	# end: auto-generated types

	pass


def on_doctype_update():
	frappe.db.add_unique("Commera Wishlist Item", ["user", "product"])
