import frappe
from frappe import _
from frappe.utils import validate_url
from frappe.utils.data import cstr, flt, get_datetime, today

from commera.shipping.exceptions import PartialBookingError
from commera.shipping.providers import get_provider
from commera.shipping.status import AWAITING_PICKUP_STATUSES, can_advance, is_terminal, validate_status
from commera.shipping.units import normalise_parcels
from commera.shipping.utils import get_address_payload

CANCELLABLE_STATUSES = ("Draft", *AWAITING_PICKUP_STATUSES)

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


def validate_carrier_cancel(shipment):
	if (
		shipment.custom_order_ref
		and shipment.custom_shipment_status in CANCELLABLE_STATUSES
		and not shipment.flags.cancelling_with_carrier
	):
		frappe.throw(
			_(
				"This shipment is booked with {0}. Use Cancel With Carrier so the label is cancelled too."
			).format(frappe.bold(shipment.custom_shipping_provider)),
			title=_("Booked With Carrier"),
		)


def validate_tracking_url(shipment):
	if shipment.tracking_url:
		validate_url(shipment.tracking_url, throw=True, valid_schemes=("http", "https"))


def sync_erpnext_status(shipment):
	shipment.service_provider = shipment.custom_shipping_provider or shipment.service_provider
	shipment.tracking_status = TRACKING_STATUSES.get(shipment.custom_shipment_status, "")
	shipment.tracking_status_info = shipment.custom_provider_status
	if shipment.docstatus == 1:
		shipment.status = get_erpnext_status(shipment)


def get_erpnext_status(shipment) -> str:
	if shipment.custom_shipment_status == "Cancelled":
		return "Cancelled"
	if shipment.custom_shipment_status in COMPLETED_STATUSES:
		return "Completed"
	return "Booked" if shipment.awb_number else "Submitted"


def get_controller(shipment):
	if not shipment.custom_shipping_provider:
		frappe.throw(
			_("{0} was shipped by a fulfilment partner, so there is no carrier to call.").format(
				shipment.name
			)
		)
	return get_provider(shipment.custom_shipping_provider)


def get_parcels(shipment) -> list[dict]:
	return normalise_parcels([parcel.as_dict() for parcel in shipment.shipment_parcel])


def get_delivery_notes(shipment) -> list[str]:
	return [row.delivery_note for row in shipment.shipment_delivery_note]


def get_customer(shipment) -> frappe._dict:
	if delivery_notes := get_delivery_notes(shipment):
		return frappe.db.get_value(
			"Delivery Note",
			delivery_notes[0],
			["customer_name as name", "contact_mobile as phone", "contact_email as email"],
			as_dict=True,
		)
	return frappe.db.get_value(
		"Sales Order",
		shipment.custom_sales_order,
		["customer_name as name", "contact_phone as phone", "contact_email as email"],
		as_dict=True,
	)


def get_declared_value(shipment) -> float:
	if delivery_notes := get_delivery_notes(shipment):
		return flt(
			sum(frappe.get_all("Delivery Note", {"name": ("in", delivery_notes)}, pluck="grand_total"))
		)
	return flt(frappe.db.get_value("Sales Order", shipment.custom_sales_order, "grand_total"))


def get_shipment_payload(shipment) -> dict:
	customer = get_customer(shipment) or frappe._dict()
	return {
		"reference": shipment.name,
		"order_reference": shipment.custom_sales_order or shipment.name,
		"service_code": shipment.custom_service_code,
		"origin": get_address_payload(shipment.pickup_address_name),
		"destination": get_address_payload(shipment.delivery_address_name, customer.name),
		"parcels": get_parcels(shipment),
		"declared_value": get_declared_value(shipment),
		"currency": shipment.custom_currency,
		"cod": bool(shipment.custom_cod),
		"cod_amount": flt(shipment.custom_cod_amount),
		"customer": {"name": customer.name, "phone": customer.phone, "email": customer.email},
	}


def lock_booking(shipment):
	frappe.db.get_value("Shipment", shipment.name, ["awb_number", "custom_order_ref"], for_update=True)
	shipment.reload()


@frappe.whitelist()
def book(shipment: str) -> dict:
	shipment_doc = frappe.get_doc("Shipment", shipment)
	shipment_doc.check_permission("submit")
	lock_booking(shipment_doc)

	if shipment_doc.awb_number:
		frappe.throw(
			_("This shipment is already booked with AWB {0}").format(frappe.bold(shipment_doc.awb_number)),
			title=_("Already Booked"),
		)
	# Only a Draft is booked: a cancelled partial booking must not be finished at the carrier.
	if shipment_doc.docstatus == 2 or shipment_doc.custom_shipment_status != "Draft":
		frappe.throw(
			_("A shipment in status {0} cannot be booked").format(
				frappe.bold(_(shipment_doc.custom_shipment_status))
			),
			title=_("Booking Not Allowed"),
		)
	if not shipment_doc.custom_service_code:
		frappe.throw(_("Select a shipping service before booking"))

	controller = get_controller(shipment_doc)
	if not controller.supports("booking"):
		frappe.throw(
			_("{0} cannot book shipments").format(frappe.bold(shipment_doc.custom_shipping_provider))
		)
	resuming = bool(shipment_doc.custom_order_ref)
	if resuming and not controller.supports("resume"):
		frappe.throw(
			_(
				"An order for this shipment already exists at {0} ({1}), and it cannot finish a partial"
				" booking. Cancel that order in the carrier's dashboard before trying again."
			).format(
				frappe.bold(shipment_doc.custom_shipping_provider), frappe.bold(shipment_doc.custom_order_ref)
			),
			title=_("Partial Booking"),
		)

	if shipment_doc.docstatus == 0:
		shipment_doc.flags.ignore_permissions = True
		shipment_doc.submit()

	request_log = frappe.get_doc(
		{
			"doctype": "Integration Request",
			"integration_request_service": f"{shipment_doc.custom_shipping_provider} Booking",
			"data": frappe.as_json(
				{"shipment": shipment_doc.name, "service_code": shipment_doc.custom_service_code}
			),
			"reference_doctype": shipment_doc.doctype,
			"reference_docname": shipment_doc.name,
		}
	).insert(ignore_permissions=True)

	try:
		if resuming:
			result = controller.resume_booking(
				shipment_doc.custom_order_ref, shipment_doc.shipment_id, shipment_doc.custom_service_code
			)
		else:
			result = controller.create_shipment(get_shipment_payload(shipment_doc))
	except PartialBookingError as partial:
		record_partial_booking(shipment_doc, partial.booking)
		request_log.db_set("status", "Failed", update_modified=False)
		raise
	except Exception:
		request_log.db_set("status", "Failed", update_modified=False)
		raise

	apply_booking_result(shipment_doc, result)
	request_log.db_set("status", "Completed", update_modified=False)
	return {
		"awb": shipment_doc.awb_number,
		"label_url": shipment_doc.custom_label_url,
		"status": shipment_doc.custom_shipment_status,
	}


def record_partial_booking(shipment, booking: dict):
	if not booking:
		return
	for field, value in (
		("custom_order_ref", booking.get("order_ref")),
		("shipment_id", booking.get("shipment_ref")),
	):
		if value:
			shipment.db_set(field, value, update_modified=False, commit=True)


def apply_booking_result(shipment, result: dict):
	shipment.custom_order_ref = result.get("order_ref")
	shipment.shipment_id = result.get("shipment_ref")
	shipment.awb_number = result.get("awb")
	shipment.carrier = result.get("carrier")
	shipment.custom_label_url = result.get("label_url")
	shipment.shipment_amount = flt(result.get("cost_amount"))
	shipment.custom_cost_currency = result.get("cost_currency")
	shipment.custom_tracking_ref = result.get("tracking_ref")
	shipment.custom_provider_status = result.get("status")
	# book() only runs on a Draft, which a carrier webhook can move on while the call is in flight.
	if can_advance(shipment.custom_shipment_status, "Ready To Ship"):
		shipment.custom_shipment_status = "Ready To Ship"
	shipment.save(ignore_permissions=True)


@frappe.whitelist()
def cancel_booking(shipment: str) -> dict:
	shipment_doc = frappe.get_doc("Shipment", shipment)
	shipment_doc.check_permission("cancel")
	lock_booking(shipment_doc)

	if not shipment_doc.custom_order_ref:
		frappe.throw(_("This shipment was never booked, so there is nothing to cancel"))
	if shipment_doc.custom_shipment_status not in CANCELLABLE_STATUSES:
		frappe.throw(
			_("A shipment in status {0} can no longer be cancelled with the carrier").format(
				frappe.bold(_(shipment_doc.custom_shipment_status))
			),
			title=_("Cancellation Not Allowed"),
		)

	controller = get_controller(shipment_doc)
	if not controller.supports("cancel"):
		frappe.throw(
			_("{0} cannot cancel shipments").format(frappe.bold(shipment_doc.custom_shipping_provider))
		)

	if shipment_doc.docstatus == 1:
		shipment_doc.flags.ignore_permissions = True
		shipment_doc.flags.cancelling_with_carrier = True
		shipment_doc.cancel()
	result = controller.cancel_shipment(
		shipment_doc.custom_order_ref, shipment_ref=shipment_doc.shipment_id, awb=shipment_doc.awb_number
	)
	shipment_doc.db_set(
		{"custom_shipment_status": "Cancelled", "custom_provider_status": (result or {}).get("status")}
	)
	return {"status": shipment_doc.custom_shipment_status}


@frappe.whitelist()
def sync_status(shipment: str) -> str:
	shipment_doc = frappe.get_doc("Shipment", shipment)
	shipment_doc.check_permission("write")
	if not shipment_doc.awb_number:
		frappe.throw(_("This shipment has no AWB yet, so there is nothing to track"))

	controller = get_controller(shipment_doc)
	if not controller.supports("tracking"):
		frappe.throw(
			_("{0} cannot track shipments").format(frappe.bold(shipment_doc.custom_shipping_provider))
		)
	tracking = controller.get_tracking(
		shipment_doc.awb_number,
		shipment_ref=shipment_doc.shipment_id,
		tracking_ref=shipment_doc.custom_tracking_ref,
	)

	lock_booking(shipment_doc)
	apply_status(
		shipment_doc,
		(tracking or {}).get("status"),
		provider_status=(tracking or {}).get("provider_status"),
		events=(tracking or {}).get("events"),
	)
	return shipment_doc.custom_shipment_status


@frappe.whitelist()
def schedule_pickup(shipment: str, pickup_date: str | None = None) -> dict:
	shipment_doc = frappe.get_doc("Shipment", shipment)
	shipment_doc.check_permission("write")
	lock_booking(shipment_doc)
	controller = get_controller(shipment_doc)
	if not controller.supports("pickup"):
		frappe.throw(
			_("{0} cannot schedule pickups").format(frappe.bold(shipment_doc.custom_shipping_provider))
		)
	if not shipment_doc.shipment_id:
		frappe.throw(_("Book this shipment before scheduling a pickup"))
	validate_awaiting_pickup(
		shipment_doc, _("A pickup can no longer be scheduled for a shipment in status {0}")
	)

	result = controller.schedule_pickup(shipment_doc.shipment_id, pickup_date=pickup_date or today())
	shipment_doc.custom_pickup_ref = (result or {}).get("pickup_ref")
	shipment_doc.pickup_date = (result or {}).get("scheduled_date") or pickup_date or today()
	if can_advance(shipment_doc.custom_shipment_status, "Pickup Scheduled"):
		shipment_doc.custom_shipment_status = "Pickup Scheduled"
	shipment_doc.save(ignore_permissions=True)
	return result or {}


@frappe.whitelist()
def generate_manifest(shipment: str) -> dict:
	shipment_doc = frappe.get_doc("Shipment", shipment)
	shipment_doc.check_permission("write")
	lock_booking(shipment_doc)
	controller = get_controller(shipment_doc)
	if not controller.supports("manifest"):
		frappe.throw(
			_("{0} cannot generate manifests").format(frappe.bold(shipment_doc.custom_shipping_provider))
		)
	if not shipment_doc.shipment_id:
		frappe.throw(_("Book this shipment before generating a manifest"))
	validate_awaiting_pickup(
		shipment_doc, _("A manifest can no longer be generated for a shipment in status {0}")
	)

	result = controller.generate_manifest([shipment_doc.shipment_id])
	shipment_doc.db_set("custom_manifest_url", (result or {}).get("manifest_url"))
	return result or {}


def validate_awaiting_pickup(shipment, message: str):
	if shipment.docstatus == 2 or shipment.custom_shipment_status not in AWAITING_PICKUP_STATUSES:
		frappe.throw(message.format(frappe.bold(_(shipment.custom_shipment_status))))


def apply_webhook_status(
	shipment,
	status: str,
	event_id: str | None = None,
	events: list | None = None,
	provider_status: str | None = None,
) -> bool:
	lock_booking(shipment)

	if event_id and shipment.custom_last_webhook_event_id == event_id:
		return False

	return apply_status(shipment, status, provider_status=provider_status, events=events, event_id=event_id)


def apply_status(
	shipment,
	status: str | None,
	provider_status: str | None = None,
	events: list | None = None,
	event_id: str | None = None,
) -> bool:
	appended = append_tracking_events(shipment, events)
	advanced = bool(status) and can_advance(shipment.custom_shipment_status, status)

	if advanced:
		validate_status(status)
		shipment.custom_shipment_status = status
	elif (
		status and status != shipment.custom_shipment_status and is_terminal(shipment.custom_shipment_status)
	):
		frappe.log_error(
			title=f"Shipment {shipment.name} status conflict",
			message=f"stored: {shipment.custom_shipment_status}, carrier reported: {status}",
		)

	describes_current_state = bool(status) and status == shipment.custom_shipment_status
	if describes_current_state:
		if provider_status:
			shipment.custom_provider_status = provider_status
		if event_id:
			shipment.custom_last_webhook_event_id = event_id

	if advanced or appended or describes_current_state:
		shipment.flags.ignore_mandatory = True
		shipment.save(ignore_permissions=True)
	return advanced


def append_tracking_events(shipment, events: list | None) -> bool:
	if not events:
		return False

	seen = {get_event_key(event.as_dict()) for event in shipment.custom_tracking_events}
	appended = False
	for event in events:
		key = get_event_key(event)
		if key in seen:
			continue
		shipment.append(
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
	return frappe.get_all(
		"Shipment",
		filters={"custom_sales_order": cstr(sales_order), "docstatus": ("<", 2), **filters},
		fields=fields or ["name"],
		order_by="creation desc",
	)
