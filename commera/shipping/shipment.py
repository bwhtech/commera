import frappe
from frappe import _
from frappe.integrations.utils import create_request_log
from frappe.utils import validate_url
from frappe.utils.data import cstr, flt, get_datetime, today

from commera.shipping.exceptions import PartialBookingError
from commera.shipping.providers import get_provider
from commera.shipping.status import can_advance, is_terminal, validate_status
from commera.shipping.units import normalise_parcels
from commera.shipping.utils import get_address_payload

CANCELLABLE_STATUSES = ("Draft", "Ready To Ship", "Pickup Scheduled")

# ERPNext's coarse tracking status for each Commera shipment status.
TRACKING_STATUSES = {
	"Pickup Scheduled": "In Progress",
	"In Transit": "In Progress",
	"Out For Delivery": "In Progress",
	"Undelivered": "In Progress",
	"RTO": "Returned",
	"Delivered": "Delivered",
	"Lost": "Lost",
}
COMPLETED_STATUSES = ("Delivered", "Lost")


class CommeraShipment:
	"""Carrier booking and tracking on ERPNext's Shipment. Commera owns `custom_shipment_status`; ERPNext's
	`status` and `tracking_status` follow it."""

	def validate(self):
		super().validate()
		self.validate_tracking_url()
		self.sync_erpnext_status()

	def before_update_after_submit(self):
		super().before_update_after_submit()
		self.validate_tracking_url()
		self.sync_erpnext_status()

	def on_submit(self):
		super().on_submit()
		self.db_set("status", self.get_erpnext_status())

	def validate_tracking_url(self):
		# Shoppers open this link from the storefront, so only web links are stored.
		if self.tracking_url:
			validate_url(self.tracking_url, throw=True, valid_schemes=("http", "https"))

	def sync_erpnext_status(self):
		self.service_provider = self.custom_shipping_provider or self.service_provider
		self.tracking_status = TRACKING_STATUSES.get(self.custom_shipment_status, "")
		self.tracking_status_info = self.custom_provider_status
		if self.docstatus == 1:
			self.status = self.get_erpnext_status()

	def get_erpnext_status(self) -> str:
		if self.custom_shipment_status == "Cancelled":
			return "Cancelled"
		if self.custom_shipment_status in COMPLETED_STATUSES:
			return "Completed"
		return "Booked" if self.awb_number else "Submitted"

	def get_controller(self):
		if not self.custom_shipping_provider:
			frappe.throw(
				_("{0} was shipped by a fulfilment partner, so there is no carrier to call.").format(
					self.name
				)
			)
		return get_provider(self.custom_shipping_provider)

	def get_parcels(self) -> list[dict]:
		return normalise_parcels([parcel.as_dict() for parcel in self.shipment_parcel])

	def get_delivery_notes(self) -> list[str]:
		return [row.delivery_note for row in self.shipment_delivery_note]

	def get_customer(self) -> frappe._dict:
		"""Who receives the parcel: the Delivery Note's contact, else the Sales Order's."""
		if delivery_notes := self.get_delivery_notes():
			return frappe.db.get_value(
				"Delivery Note",
				delivery_notes[0],
				["customer_name as name", "contact_mobile as phone", "contact_email as email"],
				as_dict=True,
			)
		return frappe.db.get_value(
			"Sales Order",
			self.custom_sales_order,
			["customer_name as name", "contact_phone as phone", "contact_email as email"],
			as_dict=True,
		)

	def get_declared_value(self) -> float:
		"""The goods' value in `custom_currency`. ERPNext's value_of_goods is in the company currency."""
		if delivery_notes := self.get_delivery_notes():
			return flt(
				sum(frappe.get_all("Delivery Note", {"name": ("in", delivery_notes)}, pluck="grand_total"))
			)
		return flt(frappe.db.get_value("Sales Order", self.custom_sales_order, "grand_total"))

	def get_shipment_payload(self) -> dict:
		customer = self.get_customer() or frappe._dict()
		return {
			"reference": self.name,
			"order_reference": self.custom_sales_order or self.name,
			"service_code": self.custom_service_code,
			"origin": get_address_payload(self.pickup_address_name),
			"destination": get_address_payload(self.delivery_address_name, customer.name),
			"parcels": self.get_parcels(),
			"declared_value": self.get_declared_value(),
			"currency": self.custom_currency,
			"cod": bool(self.custom_cod),
			"cod_amount": flt(self.custom_cod_amount),
			"customer": {"name": customer.name, "phone": customer.phone, "email": customer.email},
		}

	def lock_booking(self):
		"""Take a row lock and reload, so two concurrent bookings cannot both pass the already-booked
		guard. Held until the transaction commits."""
		frappe.db.get_value("Shipment", self.name, ["awb_number", "custom_order_ref"], for_update=True)
		self.reload()

	@frappe.whitelist()
	def book(self) -> dict:
		"""Book the consignment and buy its label. Resumes an order a previous attempt left at the
		carrier instead of creating a second one."""
		self.lock_booking()

		if self.awb_number:
			frappe.throw(
				_("This shipment is already booked with AWB {0}").format(frappe.bold(self.awb_number)),
				title=_("Already Booked"),
			)
		if not self.custom_service_code:
			frappe.throw(_("Select a shipping service before booking"))

		controller = self.get_controller()
		if not controller.supports("booking"):
			frappe.throw(_("{0} cannot book shipments").format(frappe.bold(self.custom_shipping_provider)))
		resuming = bool(self.custom_order_ref)
		if resuming and not controller.supports("resume"):
			frappe.throw(
				_(
					"An order for this shipment already exists at {0} ({1}), and it cannot finish a partial"
					" booking. Cancel that order in the carrier's dashboard before trying again."
				).format(frappe.bold(self.custom_shipping_provider), frappe.bold(self.custom_order_ref)),
				title=_("Partial Booking"),
			)

		# Submitted before the carrier call, so ERPNext's checks refuse a bad shipment before a label is
		# bought. A carrier failure rolls the submit back.
		if self.docstatus == 0:
			self.flags.ignore_permissions = True
			self.submit()

		# ponytail: the intent log shares this transaction, so a crash between the carrier call and the
		# commit loses the record of a label that was really bought; reconcile from the carrier's own
		# dashboard. Committing it first would release the row lock and re-open the double-booking window.
		request_log = create_request_log(
			{"shipment": self.name, "service_code": self.custom_service_code},
			service_name=f"{self.custom_shipping_provider} Booking",
			reference_doctype=self.doctype,
			reference_docname=self.name,
		)

		try:
			if resuming:
				result = controller.resume_booking(
					self.custom_order_ref, self.shipment_id, self.custom_service_code
				)
			else:
				result = controller.create_shipment(self.get_shipment_payload())
		except PartialBookingError as partial:
			# Committed so the handles survive the rollback this exception triggers; else the retry books
			# a second consignment.
			self.record_partial_booking(partial.booking)
			request_log.db_set("status", "Failed", update_modified=False)
			raise
		except Exception:
			request_log.db_set("status", "Failed", update_modified=False)
			raise

		self.apply_booking_result(result)
		request_log.db_set("status", "Completed", update_modified=False)
		return {
			"awb": self.awb_number,
			"label_url": self.custom_label_url,
			"status": self.custom_shipment_status,
		}

	def record_partial_booking(self, booking: dict):
		if not booking:
			return
		for field, value in (
			("custom_order_ref", booking.get("order_ref")),
			("shipment_id", booking.get("shipment_ref")),
		):
			if value:
				self.db_set(field, value, update_modified=False, commit=True)

	def apply_booking_result(self, result: dict):
		self.custom_order_ref = result.get("order_ref")
		self.shipment_id = result.get("shipment_ref")
		self.awb_number = result.get("awb")
		self.carrier = result.get("carrier")
		self.custom_label_url = result.get("label_url")
		self.shipment_amount = flt(result.get("cost_amount"))
		self.custom_cost_currency = result.get("cost_currency")
		# Optional: only carriers whose tracking handle differs from the AWB report one.
		self.custom_tracking_ref = result.get("tracking_ref")
		# The carrier may report its own booked state, but the ladder position is ours: a booked
		# consignment is Ready To Ship until a carrier scan says otherwise.
		self.custom_provider_status = result.get("status")
		self.custom_shipment_status = "Ready To Ship"
		self.save(ignore_permissions=True)

	@frappe.whitelist()
	def cancel_booking(self) -> dict:
		self.lock_booking()

		if not self.custom_order_ref:
			frappe.throw(_("This shipment was never booked, so there is nothing to cancel"))
		if self.custom_shipment_status not in CANCELLABLE_STATUSES:
			frappe.throw(
				_("A shipment in status {0} can no longer be cancelled with the carrier").format(
					frappe.bold(_(self.custom_shipment_status))
				),
				title=_("Cancellation Not Allowed"),
			)

		controller = self.get_controller()
		if not controller.supports("cancel"):
			frappe.throw(_("{0} cannot cancel shipments").format(frappe.bold(self.custom_shipping_provider)))

		# Cancelled before the carrier call, so a refusal here rolls back before the booking is lost.
		if self.docstatus == 1:
			self.flags.ignore_permissions = True
			self.cancel()
		result = controller.cancel_shipment(
			self.custom_order_ref, shipment_ref=self.shipment_id, awb=self.awb_number
		)
		self.db_set(
			{"custom_shipment_status": "Cancelled", "custom_provider_status": (result or {}).get("status")}
		)
		return {"status": self.custom_shipment_status}

	@frappe.whitelist()
	def sync_status(self) -> str:
		"""Re-read the authoritative status from the carrier. Never trust a stale local state."""
		if not self.awb_number:
			frappe.throw(_("This shipment has no AWB yet, so there is nothing to track"))

		controller = self.get_controller()
		if not controller.supports("tracking"):
			frappe.throw(_("{0} cannot track shipments").format(frappe.bold(self.custom_shipping_provider)))
		tracking = controller.get_tracking(
			self.awb_number, shipment_ref=self.shipment_id, tracking_ref=self.custom_tracking_ref
		)

		# The carrier round-trip is slow, so the lock is taken after it and picks up whatever a webhook
		# committed meanwhile. Without it this save races that webhook into a TimestampMismatchError.
		self.lock_booking()
		self.apply_status(
			(tracking or {}).get("status"),
			provider_status=(tracking or {}).get("provider_status"),
			events=(tracking or {}).get("events"),
		)
		return self.custom_shipment_status

	@frappe.whitelist()
	def schedule_pickup(self, pickup_date: str | None = None) -> dict:
		controller = self.get_controller()
		if not controller.supports("pickup"):
			frappe.throw(_("{0} cannot schedule pickups").format(frappe.bold(self.custom_shipping_provider)))
		if not self.shipment_id:
			frappe.throw(_("Book this shipment before scheduling a pickup"))

		result = controller.schedule_pickup(self.shipment_id, pickup_date=pickup_date or today())
		self.custom_pickup_ref = (result or {}).get("pickup_ref")
		self.pickup_date = (result or {}).get("scheduled_date") or pickup_date or today()
		# Only a real advance: a pickup scheduled on an already-collected consignment must not drag it
		# back down the ladder.
		if can_advance(self.custom_shipment_status, "Pickup Scheduled"):
			self.custom_shipment_status = "Pickup Scheduled"
		self.save(ignore_permissions=True)
		return result or {}

	@frappe.whitelist()
	def generate_manifest(self) -> dict:
		controller = self.get_controller()
		if not controller.supports("manifest"):
			frappe.throw(
				_("{0} cannot generate manifests").format(frappe.bold(self.custom_shipping_provider))
			)
		if not self.shipment_id:
			frappe.throw(_("Book this shipment before generating a manifest"))

		result = controller.generate_manifest([self.shipment_id])
		self.db_set("custom_manifest_url", (result or {}).get("manifest_url"))
		return result or {}

	def apply_webhook_status(
		self,
		status: str,
		event_id: str | None = None,
		events: list | None = None,
		provider_status: str | None = None,
	) -> bool:
		"""Apply a verified carrier status. Return False when the event is a replay or not applicable."""
		self.lock_booking()

		if event_id and self.custom_last_webhook_event_id == event_id:
			return False

		# The replay id records only APPLIED events, so a rejected scan cannot take the replay guard from
		# the event that did take effect.
		return self.apply_status(status, provider_status=provider_status, events=events, event_id=event_id)

	def apply_status(
		self,
		status: str | None,
		provider_status: str | None = None,
		events: list | None = None,
		event_id: str | None = None,
	) -> bool:
		"""Move the shipment along the ladder, recording scans either way. Returns whether `status` was
		applied."""
		appended = self.append_tracking_events(events)
		advanced = bool(status) and can_advance(self.custom_shipment_status, status)

		if advanced:
			validate_status(status)
			self.custom_shipment_status = status
		elif status and status != self.custom_shipment_status and is_terminal(self.custom_shipment_status):
			# Worth knowing about: the carrier disagrees with a state we already treated as final.
			frappe.log_error(
				title=f"Shipment {self.name} status conflict",
				message=f"stored: {self.custom_shipment_status}, carrier reported: {status}",
			)

		# Record the carrier wording and replay id only when this event matches the current status, so a
		# stale scan cannot relabel the shipment or claim the replay slot.
		describes_current_state = bool(status) and status == self.custom_shipment_status
		if describes_current_state:
			if provider_status:
				self.custom_provider_status = provider_status
			if event_id:
				self.custom_last_webhook_event_id = event_id

		if advanced or appended or describes_current_state:
			self.save(ignore_permissions=True)
		return advanced

	def append_tracking_events(self, events: list | None) -> bool:
		"""Add scans we have not already recorded. Returns whether anything was added."""
		if not events:
			return False

		seen = {get_event_key(event.as_dict()) for event in self.custom_tracking_events}
		appended = False
		for event in events:
			key = get_event_key(event)
			if key in seen:
				continue
			self.append(
				"custom_tracking_events",
				{
					"timestamp": get_datetime(event.get("timestamp")) if event.get("timestamp") else None,
					"status": event.get("status"),
					"location": event.get("location"),
					"message": event.get("message"),
					"event_id": event.get("event_id"),
				},
			)
			seen.add(key)
			appended = True
		return appended


def get_event_key(event: dict) -> tuple:
	"""Identity of a scan: its event id, else its fields. Timestamps go through get_datetime because stored
	rows hold datetimes and payloads hold strings."""
	if event.get("event_id"):
		return ("id", event["event_id"])
	timestamp = event.get("timestamp")
	return (
		"scan",
		str(get_datetime(timestamp)) if timestamp else None,
		event.get("status"),
		event.get("message"),
	)


def get_order_shipments(sales_order: str, fields: list | None = None, **filters) -> list[frappe._dict]:
	"""The order's live shipments, newest first."""
	return frappe.get_all(
		"Shipment",
		filters={"custom_sales_order": cstr(sales_order), "docstatus": ("<", 2), **filters},
		fields=fields or ["name"],
		order_by="creation desc",
	)
