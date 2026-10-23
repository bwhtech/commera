import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.data import cint

from commera.discounts.codes import normalize_code

MAX_CODE_LENGTH = 64


class CommeraDiscountCode(Document):
	def before_insert(self):
		self.code = normalize_code(self.code)
		if not self.code or len(self.code) > MAX_CODE_LENGTH or any(char.isspace() for char in self.code):
			frappe.throw(_("A code needs 1 to {0} characters and no spaces.").format(MAX_CODE_LENGTH))
		if frappe.db.exists("Commera Discount Code", self.code):
			frappe.throw(_("The code {0} is already in use.").format(self.code), frappe.DuplicateEntryError)

	def validate(self):
		if frappe.get_cached_value("Commera Discount", self.discount, "method") != "Code":
			frappe.throw(_("Only a code discount takes codes."))
		if not self.is_new() and self.has_value_changed("discount") and cint(self.times_used):
			frappe.throw(_("{0} has been used, so it stays with its discount.").format(self.name))
