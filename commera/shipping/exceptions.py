import frappe


class PartialBookingError(frappe.ValidationError):
	"""A booking that created something at the provider, then failed. `booking` holds the handles the
	caller must persist, or a retry creates a second order for one parcel."""

	def __init__(self, message: str, booking: dict | None = None):
		super().__init__(message)
		self.booking = booking or {}
