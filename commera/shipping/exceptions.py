import frappe


class PartialBookingError(frappe.ValidationError):
	"""A booking that failed after creating something at the provider; the caller must persist `booking`."""

	def __init__(self, message: str, booking: dict | None = None):
		super().__init__(message)
		self.booking = booking or {}
