# Copyright (c) 2026, Build With Hussain and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.integrations.utils import create_request_log
from frappe.model.document import Document
from frappe.utils import validate_url
from frappe.utils.data import cint, flt, get_datetime, today

from commera.shipping.exceptions import PartialBookingError
from commera.shipping.status import can_advance, is_terminal, validate_status
from commera.shipping.units import DEFAULT_VOLUMETRIC_DIVISOR, billable_weight, normalise_parcels
from commera.shipping.utils import get_address_payload

CANCELLABLE_STATUSES = ("Draft", "Ready To Ship", "Pickup Scheduled")


class ShippingRequest(Document):
	def validate(self):
		self.validate_origin_address()
		self.validate_tracking_url()
		self.set_billable_weight()

	def validate_origin_address(self):
		# A fulfilment partner ships from its own warehouse, which the store does not know.
		if self.provider and not self.origin_address:
			frappe.throw(_("Set a Pickup Address to ship with {0}.").format(frappe.bold(self.provider)))

	def validate_tracking_url(self):
		# Shoppers open this link from the storefront, so only web links are stored.
		if self.tracking_url:
			validate_url(self.tracking_url, throw=True, valid_schemes=("http", "https"))

	def set_billable_weight(self):
		self.billable_weight = billable_weight(self.get_parcels(), self.get_volumetric_divisor())

	def get_volumetric_divisor(self) -> int:
		"""The divisor is carrier policy, so the provider's own settings own it."""
		if not self.provider:
			return DEFAULT_VOLUMETRIC_DIVISOR
		divisor = cint(getattr(self.get_controller(), "volumetric_divisor", 0))
		return divisor or DEFAULT_VOLUMETRIC_DIVISOR

	def get_controller(self):
		if not self.provider:
			frappe.throw(
				_("{0} was shipped by a fulfilment partner, so there is no carrier to call.").format(
					self.name
				)
			)
		provider_settings = frappe.get_cached_value(
			"Shipping Provider Profile", self.provider, "provider_settings"
		)
		return frappe.get_single(provider_settings)

	def get_parcels(self) -> list[dict]:
		return normalise_parcels([parcel.as_dict() for parcel in self.parcels])

	def get_shipment_payload(self) -> dict:
		return {
			"reference": self.name,
			"order_reference": self.ref_docname,
			"service_code": self.service_code,
			"origin": get_address_payload(self.origin_address),
			"destination": get_address_payload(self.destination_address, self.customer_name),
			"parcels": self.get_parcels(),
			"declared_value": flt(self.declared_value),
			"currency": self.currency,
			"cod": bool(self.cod),
			"cod_amount": flt(self.cod_amount),
			"customer": {
				"name": self.customer_name,
				"phone": self.customer_phone,
				"email": self.customer_email,
			},
		}

	def lock_booking(self):
		"""Take a row lock and reload, so two concurrent bookings cannot both pass the already-booked
		guard. Held until the transaction commits."""
		frappe.db.get_value("Shipping Request", self.name, ["awb", "order_ref", "status"], for_update=True)
		self.reload()

	@frappe.whitelist()
	def book(self) -> dict:
		"""Book the consignment and buy its label. Resumes an order a previous attempt left at the
		provider instead of creating a second one."""
		self.lock_booking()

		if self.awb:
			frappe.throw(
				_("This shipment is already booked with AWB {0}").format(frappe.bold(self.awb)),
				title=_("Already Booked"),
			)
		if not self.service_code:
			frappe.throw(_("Select a shipping service before booking"))

		controller = self.get_controller()
		resuming = bool(self.order_ref)
		if resuming and not controller.supports("resume"):
			frappe.throw(
				_(
					"An order for this shipment already exists at {0} ({1}), and it cannot finish a partial"
					" booking. Cancel that order in the provider's dashboard before trying again."
				).format(frappe.bold(self.provider), frappe.bold(self.order_ref)),
				title=_("Partial Booking"),
			)

		# ponytail: the intent log shares this transaction, so a crash between the provider call and the
		# commit loses the record of a label that was really bought; reconcile from the provider's own
		# dashboard. Committing it first would release the row lock and re-open the double-booking window.
		request_log = create_request_log(
			{"shipping_request": self.name, "service_code": self.service_code},
			service_name=f"{self.provider} Booking",
			reference_doctype=self.doctype,
			reference_docname=self.name,
		)

		try:
			if resuming:
				result = controller.resume_booking(self.order_ref, self.shipment_ref, self.service_code)
			else:
				result = controller.create_shipment(self.get_shipment_payload())
		except PartialBookingError as partial:
			# db_set so the handles survive the rollback this exception triggers; else the retry books a
			# second consignment.
			self.record_partial_booking(partial.booking)
			request_log.db_set("status", "Failed", update_modified=False)
			raise
		except Exception:
			request_log.db_set("status", "Failed", update_modified=False)
			raise

		self.apply_booking_result(result)
		request_log.db_set("status", "Completed", update_modified=False)
		return {"awb": self.awb, "label_url": self.label_url, "status": self.status}

	def record_partial_booking(self, booking: dict):
		"""Persist the handles a half-finished booking left at the provider. db_set, not save, so they
		survive the rollback of the re-raise."""
		if not booking:
			return
		for field in ("order_ref", "shipment_ref"):
			if booking.get(field):
				self.db_set(field, booking[field], update_modified=False, commit=True)

	def apply_booking_result(self, result: dict):
		self.order_ref = result.get("order_ref")
		self.shipment_ref = result.get("shipment_ref")
		self.awb = result.get("awb")
		self.carrier = result.get("carrier")
		self.label_url = result.get("label_url")
		self.cost_amount = flt(result.get("cost_amount"))
		self.cost_currency = result.get("cost_currency")
		# Optional: only providers whose tracking handle differs from the AWB report one.
		self.tracking_ref = result.get("tracking_ref")
		# The provider may report its own booked state, but the ladder position is ours: a booked
		# consignment is Ready To Ship until a carrier scan says otherwise.
		self.provider_status = result.get("status")
		self.status = "Ready To Ship"
		self.save(ignore_permissions=True)

	@frappe.whitelist()
	def cancel_booking(self) -> dict:
		self.lock_booking()

		if not self.order_ref:
			frappe.throw(_("This shipment was never booked, so there is nothing to cancel"))
		if self.status not in CANCELLABLE_STATUSES:
			frappe.throw(
				_("A shipment in status {0} can no longer be cancelled with the carrier").format(
					frappe.bold(_(self.status))
				),
				title=_("Cancellation Not Allowed"),
			)

		result = self.get_controller().cancel_shipment(
			self.order_ref, shipment_ref=self.shipment_ref, awb=self.awb
		)
		self.status = "Cancelled"
		self.provider_status = (result or {}).get("status")
		self.save(ignore_permissions=True)
		return {"status": self.status}

	@frappe.whitelist()
	def sync_status(self) -> str:
		"""Re-read the authoritative status from the provider. Never trust a stale local state."""
		if not self.awb:
			frappe.throw(_("This shipment has no AWB yet, so there is nothing to track"))

		tracking = self.get_controller().get_tracking(
			self.awb, shipment_ref=self.shipment_ref, tracking_ref=self.tracking_ref
		)

		# The provider round-trip is slow, so the lock is taken after it and picks up whatever a webhook
		# committed meanwhile. Without it this save races that webhook into a TimestampMismatchError.
		self.lock_booking()
		self.apply_status(
			(tracking or {}).get("status"),
			provider_status=(tracking or {}).get("provider_status"),
			events=(tracking or {}).get("events"),
		)
		return self.status

	@frappe.whitelist()
	def schedule_pickup(self, pickup_date: str | None = None) -> dict:
		controller = self.get_controller()
		if not controller.supports("pickup"):
			frappe.throw(_("{0} cannot schedule pickups").format(frappe.bold(self.provider)))
		if not self.shipment_ref:
			frappe.throw(_("Book this shipment before scheduling a pickup"))

		result = controller.schedule_pickup(self.shipment_ref, pickup_date=pickup_date or today())
		self.pickup_ref = (result or {}).get("pickup_ref")
		self.pickup_date = (result or {}).get("scheduled_date") or pickup_date or today()
		# Only a real advance: a pickup scheduled on an already-collected consignment must not drag it
		# back down the ladder.
		if can_advance(self.status, "Pickup Scheduled"):
			self.status = "Pickup Scheduled"
		self.save(ignore_permissions=True)
		return result or {}

	@frappe.whitelist()
	def generate_manifest(self) -> dict:
		controller = self.get_controller()
		if not controller.supports("manifest"):
			frappe.throw(_("{0} cannot generate manifests").format(frappe.bold(self.provider)))
		if not self.shipment_ref:
			frappe.throw(_("Book this shipment before generating a manifest"))

		result = controller.generate_manifest([self.shipment_ref])
		self.db_set("manifest_url", (result or {}).get("manifest_url"))
		return result or {}

	def apply_webhook_status(
		self,
		status: str,
		event_id: str | None = None,
		events: list | None = None,
		provider_status: str | None = None,
	) -> bool:
		"""Apply a verified provider status. Return False when the event is a replay or not applicable."""
		self.lock_booking()

		if event_id and self.last_webhook_event_id == event_id:
			return False

		# `last_webhook_event_id` records only APPLIED events, so a rejected scan cannot take the replay
		# guard from the event that did take effect.
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
		advanced = bool(status) and can_advance(self.status, status)

		if advanced:
			validate_status(status)
			self.status = status
		elif status and status != self.status and is_terminal(self.status):
			# Worth knowing about: the carrier disagrees with a state we already treated as final.
			frappe.log_error(
				title=f"Shipping Request {self.name} status conflict",
				message=f"stored: {self.status}, provider reported: {status}",
			)

		# Record the provider wording and replay id only when this event matches the current status, so a
		# stale scan cannot relabel the shipment or claim the replay slot.
		describes_current_state = bool(status) and status == self.status
		if describes_current_state:
			if provider_status:
				self.provider_status = provider_status
			if event_id:
				self.last_webhook_event_id = event_id

		if advanced or appended or describes_current_state:
			self.save(ignore_permissions=True)
		return advanced

	def append_tracking_events(self, events: list | None) -> bool:
		"""Add scans we have not already recorded. Returns whether anything was added."""
		if not events:
			return False

		seen = {self.event_key(event.as_dict()) for event in self.tracking_events}
		appended = False
		for event in events:
			key = self.event_key(event)
			if key in seen:
				continue
			self.append(
				"tracking_events",
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

	def event_key(self, event: dict) -> tuple:
		"""Identity of a scan: its event id, else its fields. Timestamps go through get_datetime because
		stored rows hold datetimes and payloads hold strings."""
		if event.get("event_id"):
			return ("id", event["event_id"])
		timestamp = event.get("timestamp")
		return (
			"scan",
			str(get_datetime(timestamp)) if timestamp else None,
			event.get("status"),
			event.get("message"),
		)
