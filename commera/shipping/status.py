import frappe
from frappe import _

# Every move a shipment can make, written out. A carrier skips steps freely (a parcel can go from Ready
# To Ship straight to Delivered), but never back down the road, except for a re-attempt after a failed
# delivery. RTO, the parcel on its way back to the store, only ends in Lost. A Draft can jump ahead too:
# a plugin or a fulfilment partner records a shipment it booked elsewhere.
IN_FLIGHT = ("In Transit", "Out For Delivery", "Undelivered", "RTO", "Delivered", "Lost")
TRANSITIONS = {
	"Draft": ("Ready To Ship", "Pickup Scheduled", *IN_FLIGHT, "Cancelled"),
	"Ready To Ship": ("Pickup Scheduled", *IN_FLIGHT, "Cancelled"),
	"Pickup Scheduled": (*IN_FLIGHT, "Cancelled"),
	"In Transit": ("Out For Delivery", "Undelivered", "RTO", "Delivered", "Lost"),
	"Out For Delivery": ("Undelivered", "RTO", "Delivered", "Lost"),
	"Undelivered": ("In Transit", "Out For Delivery", "RTO", "Delivered", "Lost"),
	"RTO": ("Lost",),
	"Delivered": (),
	"Cancelled": (),
	"Lost": (),
}
SHIPMENT_STATUSES = tuple(TRANSITIONS)
TERMINAL_STATUSES = tuple(status for status, targets in TRANSITIONS.items() if not targets)
# Booked with the carrier but not yet handed over, so the carrier can still cancel or collect it.
AWAITING_PICKUP_STATUSES = ("Ready To Ship", "Pickup Scheduled")


def validate_status(status: str):
	if status not in TRANSITIONS:
		frappe.throw(_("{0} is not a known shipment status").format(frappe.bold(status)))


def can_advance(current: str, new: str) -> bool:
	return new in TRANSITIONS.get(current or "Draft", ())


def is_terminal(status: str) -> bool:
	return status in TERMINAL_STATUSES
