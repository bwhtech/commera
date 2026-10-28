import frappe
from frappe import _

# Unmapped provider states are left out, so they can neither advance nor close a shipment.
SHIPMENT_STATUSES = (
	"Draft",
	"Ready To Ship",
	"Pickup Scheduled",
	"In Transit",
	"Out For Delivery",
	"Undelivered",
	"RTO",
	"Delivered",
	"Cancelled",
	"Lost",
)

# Carriers send scans out of order and replay history, so a status applies only when it ranks
# higher than the stored one. The three endings share the top rank.
STATUS_RANK = {
	"Draft": 0,
	"Ready To Ship": 1,
	"Pickup Scheduled": 2,
	"In Transit": 3,
	"Out For Delivery": 4,
	"Undelivered": 5,
	"RTO": 6,
	"Delivered": 7,
	"Cancelled": 7,
	"Lost": 7,
}

# Where a shipment stops. A later scan on one of these is a duplicate or a replay, and applying it would
# un-deliver a delivered order.
TERMINAL_STATUSES = ("Delivered", "Cancelled", "Lost")


def validate_status(status: str):
	if status not in STATUS_RANK:
		frappe.throw(_("{0} is not a known shipment status").format(frappe.bold(status)))


def can_advance(current: str, new: str) -> bool:
	"""Whether a provider-reported status may overwrite the stored one."""
	if new not in STATUS_RANK or new == current:
		return False
	if current in TERMINAL_STATUSES:
		return False
	return STATUS_RANK[new] > STATUS_RANK.get(current, 0)


def is_terminal(status: str) -> bool:
	return status in TERMINAL_STATUSES
