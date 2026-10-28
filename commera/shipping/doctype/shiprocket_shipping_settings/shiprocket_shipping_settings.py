# Copyright (c) 2026, Build With Hussain and contributors
# For license information, please see license.txt

import hmac

import frappe
from frappe import _
from frappe.integrations.utils import create_request_log
from frappe.model.document import Document
from frappe.utils import get_request_session
from frappe.utils.data import cint, cstr, flt, today

from commera.shipping.base_class import ShippingProviderBase
from commera.shipping.exceptions import PartialBookingError
from commera.shipping.units import billable_weight, enclosing_dimensions, to_system_datetime

SHIPROCKET_BASE_URL = "https://apiv2.shiprocket.in/v1/external"

# Shiprocket tokens last 10 days. Cached in Redis to keep the credential out of the database;
# expired early so a long request cannot race the boundary.
TOKEN_CACHE_KEY = "commera:shiprocket_token"
TOKEN_TTL_SECONDS = 8 * 24 * 60 * 60

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_CURRENCY = "INR"

# Unmapped states are logged, not applied, so they cannot advance or close a shipment.
# Compared casefolded: the API capitalisation is inconsistent.
SHIPROCKET_STATUS_MAP = {
	"new": "Ready To Ship",
	"invoiced": "Ready To Ship",
	"awb assigned": "Ready To Ship",
	"label generated": "Ready To Ship",
	"ready to ship": "Ready To Ship",
	"pickup scheduled": "Pickup Scheduled",
	"pickup generated": "Pickup Scheduled",
	"pickup queued": "Pickup Scheduled",
	"pickup rescheduled": "Pickup Scheduled",
	"picked up": "In Transit",
	"shipped": "In Transit",
	"in transit": "In Transit",
	"reached destination hub": "In Transit",
	"misroute": "In Transit",
	"out for delivery": "Out For Delivery",
	"delivered": "Delivered",
	"undelivered": "Undelivered",
	"delivery exception": "Undelivered",
	"canceled": "Cancelled",
	"cancelled": "Cancelled",
	"rto initiated": "RTO",
	"rto in transit": "RTO",
	"rto acknowledged": "RTO",
	"rto delivered": "RTO",
	"lost": "Lost",
	"damaged": "Lost",
}

# `dict(frappe.request.headers)` loses werkzeug's case-insensitivity, so this has to match the canonical
# title-case werkzeug hands over, not Shiprocket's documented lowercase spelling.
SHIPROCKET_API_KEY_HEADER = "X-Api-Key"


class ShiprocketShippingSettings(Document, ShippingProviderBase):
	label = "Shiprocket"
	blurb = "Courier aggregator for domestic India. Pincode-driven, COD supported."
	docs_url = "https://apidocs.shiprocket.in/"

	# --- HTTP ----------------------------------------------------------------

	def get_token(self, refresh: bool = False) -> str:
		if not refresh:
			cached = frappe.cache.get_value(TOKEN_CACHE_KEY)
			if cached:
				return cstr(cached)
		return self.login()

	def login(self) -> str:
		password = self.get_password("password", raise_exception=False)
		if not (self.email and password):
			frappe.throw(_("Set the Shiprocket API email and password before using this provider"))

		# Deliberately not via `request()`: that would ask for a token and recurse into login.
		response = self.send(
			"POST",
			"/auth/login",
			headers={"Content-Type": "application/json"},
			json={"email": self.email, "password": password},
		)
		token = (response or {}).get("token")
		if not token:
			frappe.throw(_("Shiprocket did not return a login token"))

		frappe.cache.set_value(TOKEN_CACHE_KEY, token, expires_in_sec=TOKEN_TTL_SECONDS)
		return cstr(token)

	def request(self, method: str, endpoint: str, payload: dict | None = None, timeout: int | None = None):
		"""Call Shiprocket, refreshing the cached token once on a 401. A token can be invalidated before
		its nominal expiry."""
		try:
			return self.authorised_send(method, endpoint, payload, timeout)
		except PermissionError:
			return self.authorised_send(method, endpoint, payload, timeout, refresh_token=True)

	def authorised_send(
		self,
		method: str,
		endpoint: str,
		payload: dict | None,
		timeout: int | None,
		refresh_token: bool = False,
	):
		headers = {
			"Authorization": f"Bearer {self.get_token(refresh=refresh_token)}",
			"Content-Type": "application/json",
		}
		if method == "GET":
			return self.send(method, endpoint, headers=headers, params=payload, timeout=timeout)
		return self.send(method, endpoint, headers=headers, json=payload, timeout=timeout)

	def send(
		self,
		method: str,
		endpoint: str,
		headers: dict,
		json: dict | None = None,
		params: dict | None = None,
		timeout: int | None = None,
	):
		"""Send one Shiprocket HTTP call. Uses `get_request_session` because `make_*_request` takes no
		timeout, and a hung call at checkout holds a worker."""
		url = f"{SHIPROCKET_BASE_URL}{endpoint}"
		try:
			response = get_request_session().request(
				method,
				url,
				headers=headers,
				json=json,
				params=params,
				timeout=timeout or DEFAULT_TIMEOUT_SECONDS,
			)
		except Exception as exception:
			self.log_request(endpoint, error=exception)
			frappe.throw(_("Could not reach Shiprocket: {0}").format(cstr(exception)))

		if response.status_code == 401:
			# Surfaced as PermissionError so `request` can tell "stale token, retry" apart from a real
			# rejection; every other non-2xx is terminal.
			raise PermissionError("Shiprocket rejected the token")

		body = self.read_body(response, endpoint)
		if not response.ok:
			message = read_shiprocket_error(body) or f"HTTP {response.status_code}"
			self.log_request(endpoint, error=message)
			frappe.throw(_("Shiprocket rejected the request: {0}").format(message))

		self.log_request(endpoint, output=summarise(body))
		return body

	def read_body(self, response, endpoint: str):
		try:
			return response.json()
		except ValueError:
			self.log_request(endpoint, error="Shiprocket returned a non-JSON body")
			frappe.throw(_("Shiprocket returned an unreadable response"))

	def log_request(self, endpoint: str, output=None, error=None):
		# The payload carries the customer's name, address and phone number, so only the endpoint and the
		# outcome are logged.
		create_request_log(
			{"endpoint": endpoint},
			service_name="Shiprocket",
			is_remote_request=True,
			reference_doctype=self.doctype,
			reference_docname=self.name,
			output=output,
			error=error,
			status="Failed" if error else "Completed",
		)

	# --- Contract ------------------------------------------------------------

	def get_rates(
		self,
		origin: dict,
		destination: dict,
		parcels: list[dict],
		cod: bool = False,
		declared_value: float = 0.0,
	) -> list[dict]:
		pickup_pincode = (origin or {}).get("pincode")
		delivery_pincode = (destination or {}).get("pincode")
		if not (pickup_pincode and delivery_pincode):
			# Shiprocket rates on pincodes only. A missing one is normal mid-checkout; the caller prices
			# from the backup charge.
			return []

		params = {
			"pickup_postcode": pickup_pincode,
			"delivery_postcode": delivery_pincode,
			"weight": billable_weight(parcels, self.get_volumetric_divisor()),
			"cod": 1 if cod else 0,
			"declared_value": flt(declared_value),
		}
		response = self.request(
			"GET",
			"/courier/serviceability/",
			params,
			timeout=cint(self.rates_timeout_seconds) or 10,
		)
		couriers = ((response or {}).get("data") or {}).get("available_courier_companies") or []
		return [self.build_rate(courier, cod) for courier in couriers if self.is_quotable(courier)]

	def is_quotable(self, courier: dict) -> bool:
		# A courier row with no id cannot be booked later, and one with no rate would be quoted to the
		# shopper as free.
		return bool(courier.get("courier_company_id")) and flt(courier.get("rate")) > 0

	def build_rate(self, courier: dict, cod: bool) -> dict:
		return {
			"service_code": cstr(courier.get("courier_company_id")),
			"service_name": courier.get("courier_name"),
			"carrier": courier.get("courier_name"),
			"amount": flt(courier.get("rate")),
			"currency": self.get_currency(),
			"transit_days": cint(courier.get("estimated_delivery_days")),
			"cod_available": bool(cint(courier.get("cod"))) if not cod else True,
		}

	def create_shipment(self, shipment: dict) -> dict:
		"""Book in three calls: order, AWB, label. No rollback exists, so each stage reports what it
		created even when a later one fails, and a label failure keeps the AWB."""
		order = self.create_order(shipment)
		shipment_ref = cstr(order.get("shipment_id"))
		order_ref = cstr(order.get("order_id"))
		if not shipment_ref:
			frappe.throw(_("Shiprocket created no shipment for this order"))

		# From here the order exists at Shiprocket. Any failure has to carry these handles back out, or the
		# next attempt creates a second order for the same parcel and orphans this one.
		booking = {"order_ref": order_ref, "shipment_ref": shipment_ref}
		try:
			awb_details = self.assign_awb(shipment_ref, shipment.get("service_code"))
		except Exception as exception:
			raise PartialBookingError(cstr(exception), booking=booking) from exception

		awb = cstr(awb_details.get("awb_code"))
		if not awb:
			raise PartialBookingError(
				_("Shiprocket assigned no AWB to shipment {0}").format(shipment_ref), booking=booking
			)

		return {
			"order_ref": order_ref,
			"shipment_ref": shipment_ref,
			"awb": awb,
			"carrier": awb_details.get("courier_name"),
			"label_url": self.generate_label(shipment_ref),
			# Shiprocket's `charges`/`rate` here is what it will invoice, which is not always the quote the
			# shopper was shown; the difference is exactly what markup and handling fees exist to absorb.
			"cost_amount": flt(awb_details.get("charges") or awb_details.get("rate")),
			"cost_currency": self.get_currency(),
			"status": order.get("status"),
		}

	def resume_booking(self, order_ref: str, shipment_ref: str, service_code: str | None = None) -> dict:
		"""Finish a booking whose order already exists at Shiprocket, without creating a second one."""
		awb_details = self.assign_awb(shipment_ref, service_code)
		awb = cstr(awb_details.get("awb_code"))
		if not awb:
			raise PartialBookingError(
				_("Shiprocket assigned no AWB to shipment {0}").format(shipment_ref),
				booking={"order_ref": order_ref, "shipment_ref": shipment_ref},
			)

		return {
			"order_ref": order_ref,
			"shipment_ref": shipment_ref,
			"awb": awb,
			"carrier": awb_details.get("courier_name"),
			"label_url": self.generate_label(shipment_ref),
			"cost_amount": flt(awb_details.get("charges") or awb_details.get("rate")),
			"cost_currency": self.get_currency(),
			"status": None,
		}

	def create_order(self, shipment: dict) -> dict:
		response = self.request("POST", "/orders/create/adhoc", self.build_order_payload(shipment))
		return response or {}

	def build_order_payload(self, shipment: dict) -> dict:
		destination = shipment.get("destination") or {}
		parcels = shipment.get("parcels") or []
		dimensions = enclosing_dimensions(parcels)
		customer_name = split_name(
			destination.get("contact_name") or shipment.get("customer", {}).get("name")
		)
		payload = {
			"order_id": shipment.get("reference"),
			"order_date": today(),
			"pickup_location": self.pickup_location,
			"billing_customer_name": customer_name["first"],
			"billing_last_name": customer_name["last"],
			"billing_address": destination.get("line1"),
			"billing_address_2": destination.get("line2") or "",
			"billing_city": destination.get("city"),
			"billing_pincode": destination.get("pincode"),
			"billing_state": destination.get("state"),
			"billing_country": destination.get("country"),
			"billing_email": destination.get("email") or "",
			"billing_phone": destination.get("phone") or "",
			"shipping_is_billing": True,
			"order_items": build_order_items(shipment),
			"payment_method": "COD" if shipment.get("cod") else "Prepaid",
			"sub_total": flt(shipment.get("declared_value")),
			"length": dimensions["length"],
			"breadth": dimensions["width"],
			"height": dimensions["height"],
			"weight": billable_weight(parcels, self.get_volumetric_divisor()),
		}
		if self.channel_id:
			payload["channel_id"] = self.channel_id
		return payload

	def assign_awb(self, shipment_ref: str, service_code: str | None) -> dict:
		payload = {"shipment_id": shipment_ref}
		if service_code:
			payload["courier_id"] = service_code
		response = self.request("POST", "/courier/assign/awb", payload) or {}
		# Shiprocket nests the useful half of this response one level down.
		return (response.get("response") or {}).get("data") or {}

	def generate_label(self, shipment_ref: str) -> str | None:
		"""Non-fatal: the AWB is already booked, and raising here would lose it. The label can be
		regenerated from the desk, so a failure is logged and the booking stands."""
		try:
			response = self.request("POST", "/courier/generate/label", {"shipment_id": [shipment_ref]})
			return (response or {}).get("label_url")
		except Exception:
			frappe.log_error(
				title="Shiprocket label generation failed",
				message=f"shipment_id: {shipment_ref}",
			)
			return None

	def cancel_shipment(
		self, order_ref: str, shipment_ref: str | None = None, awb: str | None = None
	) -> dict:
		response = self.request("POST", "/orders/cancel", {"ids": [order_ref]})
		return {"status": "Cancelled", "message": (response or {}).get("message")}

	def get_tracking(
		self, awb: str, shipment_ref: str | None = None, tracking_ref: str | None = None
	) -> dict:
		# Shiprocket tracks on the AWB itself, so it has no separate tracking handle to use.
		response = self.request("GET", f"/courier/track/awb/{awb}")
		tracking = read_tracking_data(response)
		scans = tracking.get("shipment_track_activities") or []
		provider_status = read_current_status(tracking)
		return {
			"status": map_status(provider_status),
			"provider_status": provider_status,
			"events": [build_event(scan) for scan in scans],
		}

	def handle_webhook(self, payload: bytes, headers: dict) -> dict:
		"""Shiprocket does not sign webhooks; it echoes a static `x-api-key` token. A missing configured
		token is a hard failure, not a skipped check."""
		webhook_token = self.get_password("webhook_secret", raise_exception=False)
		if not webhook_token:
			frappe.throw(_("Webhook token is not configured in Shiprocket Shipping Settings"))

		supplied_token = headers.get(SHIPROCKET_API_KEY_HEADER)
		if not supplied_token:
			frappe.throw(_("Missing {0} header").format(SHIPROCKET_API_KEY_HEADER))
		# Compared as bytes: compare_digest raises TypeError on a non-ASCII str, which would surface as an
		# unexplained TypeError instead of the mismatch this actually is.
		if not hmac.compare_digest(webhook_token.encode(), supplied_token.encode()):
			frappe.throw(_("Shiprocket webhook token does not match"))

		event = frappe.parse_json(payload.decode())
		awb = cstr(event.get("awb"))
		provider_status = cstr(event.get("current_status"))
		status = map_status(provider_status)
		if not (awb and status):
			# Either an event for something we do not track, or a status this app deliberately does not
			# map. Returning {} accepts the delivery so Shiprocket stops retrying it.
			return {}

		return {
			"awb": awb,
			"status": status,
			"provider_status": provider_status,
			# Shiprocket has no event id of its own, so the status timestamp is the closest thing to one:
			# it is what makes a redelivery of the same scan recognisable as a replay.
			"event_id": cstr(event.get("current_timestamp") or event.get("etd") or provider_status),
			"events": [build_event(scan) for scan in event.get("scans") or []],
		}

	def schedule_pickup(self, shipment_ref: str, pickup_date: str | None = None) -> dict:
		payload = {"shipment_id": [shipment_ref]}
		if pickup_date:
			payload["pickup_date"] = [pickup_date]
		response = self.request("POST", "/courier/generate/pickup", payload) or {}
		return {
			"pickup_ref": cstr(response.get("pickup_token_number")),
			"scheduled_date": (response.get("pickup_scheduled_date") or "").split(" ")[0] or pickup_date,
			"message": response.get("response"),
		}

	def generate_manifest(self, shipment_refs: list[str]) -> dict:
		response = self.request("POST", "/manifests/generate", {"shipment_id": shipment_refs}) or {}
		return {"manifest_url": response.get("manifest_url")}

	# --- Helpers -------------------------------------------------------------

	def get_currency(self) -> str:
		return self.currency or DEFAULT_CURRENCY

	def get_volumetric_divisor(self) -> int:
		return cint(self.volumetric_divisor) or 5000

	@frappe.whitelist()
	def test_connection(self) -> dict:
		"""Prove the credentials and the pickup nickname before an order depends on them."""
		self.login()
		response = self.request("GET", "/settings/company/pickup") or {}
		locations = (response.get("data") or {}).get("shipping_address") or []
		nicknames = [cstr(location.get("pickup_location")) for location in locations]
		if self.pickup_location and self.pickup_location not in nicknames:
			frappe.throw(
				_("Shiprocket has no pickup location named {0}. It knows: {1}").format(
					frappe.bold(self.pickup_location), ", ".join(nicknames) or _("none")
				)
			)
		return {"pickup_locations": nicknames}


def map_status(provider_status: str | None) -> str | None:
	return SHIPROCKET_STATUS_MAP.get(cstr(provider_status).strip().casefold())


def read_tracking_data(response) -> dict:
	"""Shiprocket returns tracking as {"<awb>": {"tracking_data": {...}}} or as a bare tracking_data."""
	if not isinstance(response, dict):
		return {}
	if "tracking_data" in response:
		return response.get("tracking_data") or {}
	for value in response.values():
		if isinstance(value, dict) and "tracking_data" in value:
			return value.get("tracking_data") or {}
	return {}


def read_current_status(tracking: dict) -> str | None:
	track = tracking.get("shipment_track") or []
	if track and isinstance(track[0], dict):
		return track[0].get("current_status")
	return tracking.get("shipment_status")


def build_event(scan: dict) -> dict:
	# Shiprocket spells the same scan differently across endpoints (`date`/`status`/`activity` from
	# tracking, `sr-status-label`/`location` from the webhook), so both spellings are read.
	return {
		"timestamp": to_system_datetime(scan.get("date") or scan.get("updated_date") or scan.get("time")),
		"status": scan.get("sr-status-label") or scan.get("status") or scan.get("sr_status_label"),
		"location": scan.get("location"),
		"message": scan.get("activity") or scan.get("sr-status-label") or scan.get("status"),
	}


def build_order_items(shipment: dict) -> list[dict]:
	"""Shiprocket rejects an order with no line items. Without Delivery Note lines, use one line for
	the whole parcel."""
	items = []
	for parcel in shipment.get("parcels") or []:
		for item in parcel.get("items") or []:
			items.append(
				{
					"name": item.get("description") or item.get("sku"),
					"sku": item.get("sku") or item.get("description"),
					"units": cint(item.get("quantity")) or 1,
					"selling_price": flt(item.get("rate")),
				}
			)
	if items:
		return items
	return [
		{
			"name": _("Order {0}").format(shipment.get("order_reference") or shipment.get("reference")),
			"sku": cstr(shipment.get("order_reference") or shipment.get("reference")),
			"units": 1,
			"selling_price": flt(shipment.get("declared_value")),
		}
	]


def split_name(full_name: str | None) -> dict:
	"""Shiprocket takes first and last name separately and rejects a blank first name."""
	parts = cstr(full_name).split()
	if not parts:
		return {"first": _("Customer"), "last": ""}
	return {"first": parts[0], "last": " ".join(parts[1:])}


def read_shiprocket_error(body) -> str | None:
	if not isinstance(body, dict):
		return None
	if message := body.get("message"):
		return cstr(message)
	errors = body.get("errors")
	if isinstance(errors, dict):
		# Shiprocket returns {"errors": {"field": ["problem", ...]}}.
		return "; ".join(f"{field}: {', '.join(map(cstr, problems))}" for field, problems in errors.items())
	if errors:
		return cstr(errors)
	return None


def summarise(body) -> dict:
	"""Shiprocket echoes the customer's name, address and phone number, so only ids are logged."""
	if not isinstance(body, dict):
		return {}
	return {
		key: body[key]
		for key in ("order_id", "shipment_id", "status", "awb_code", "current_status")
		if key in body
	}
