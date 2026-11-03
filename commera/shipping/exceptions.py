import frappe


class PartialBookingError(frappe.ValidationError):
	def __init__(self, message: str, booking: dict | None = None):
		super().__init__(message)
		self.booking = booking or {}
