# Copyright (c) 2026, Build With Hussain and contributors
# For license information, please see license.txt

import base64
import hashlib
import hmac

import frappe
from frappe import _
from frappe.integrations.utils import create_request_log
from frappe.model.document import Document
from frappe.utils import get_request_session
from frappe.utils.data import cint, cstr, flt

from commera.shipping.base_class import RateRequest, ShippingProviderBase
from commera.shipping.units import billable_weight, to_system_datetime
from commera.shipping.utils import get_provider_profile

DEFAULT_TIMEOUT_SECONDS = 30

# AfterShip needs an account and a service type to buy a label. They travel in one
# `service_code` string joined by this separator.
SERVICE_CODE_SEPARATOR = "|"

# `Exception` and `Expired` are left out on purpose: they need a human, and an unattended
# webhook must not close or advance a shipment on them.
AFTERSHIP_TAG_MAP = {
	"Pending": "Ready To Ship",
	"InfoReceived": "Ready To Ship",
	"InTransit": "In Transit",
	"OutForDelivery": "Out For Delivery",
	"AvailableForPickup": "Out For Delivery",
	"AttemptFail": "Undelivered",
	"Delivered": "Delivered",
}

# `dict(frappe.request.headers)` loses werkzeug's case-insensitivity, so this matches the canonical
# title-case werkzeug hands over rather than AfterShip's documented lowercase spelling.
AFTERSHIP_SIGNATURE_HEADER = "Aftership-Hmac-Sha256"

# ISO alpha-3 for the countries this app is likely to ship between, used only when pycountry is absent.
FALLBACK_ALPHA_3 = {
	"IN": "IND",
	"US": "USA",
	"GB": "GBR",
	"AE": "ARE",
	"SA": "SAU",
	"AU": "AUS",
	"CA": "CAN",
	"SG": "SGP",
	"DE": "DEU",
	"FR": "FRA",
}


class AfterShipShippingSettings(Document, ShippingProviderBase):
	label = "AfterShip"
	blurb = "Global labels and tracking across hundreds of carriers."
	docs_url = "https://www.aftership.com/docs/shipping/quickstart/api-quick-start"

	# --- HTTP ----------------------------------------------------------------

	def get_headers(self) -> dict:
		api_key = self.get_password("api_key", raise_exception=False)
		if not api_key:
			frappe.throw(_("Set the AfterShip API Key before using this provider"))
		return {"as-api-key": api_key, "content-type": "application/json"}

	def get_shipping_base(self) -> str:
		return self.shipping_test_host if self.test_mode else self.shipping_production_host

	def get_tracking_base(self) -> str:
		return f"{self.tracking_host}/{self.tracking_api_version}"

	def request(
		self,
		method: str,
		base: str,
		path: str,
		payload: dict | None = None,
		timeout: int | None = None,
	) -> dict:
		"""Call AfterShip and unwrap its envelope. Business errors come back as HTTP 200 with a failing
		`meta.code`."""
		url = f"{base}{path}"
		try:
			response = get_request_session().request(
				method,
				url,
				headers=self.get_headers(),
				json=payload if method != "GET" else None,
				params=payload if method == "GET" else None,
				timeout=timeout or DEFAULT_TIMEOUT_SECONDS,
			)
		except Exception as exception:
			self.log_request(path, error=exception)
			frappe.throw(_("Could not reach AfterShip: {0}").format(cstr(exception)))

		body = self.read_body(response, path)
		self.raise_for_meta(body, path)
		self.log_request(path, output=summarise(body))
		return body.get("data") or {}

	def read_body(self, response, path: str) -> dict:
		try:
			body = response.json()
		except ValueError:
			self.log_request(path, error="AfterShip returned a non-JSON body")
			frappe.throw(_("AfterShip returned an unreadable response"))
		return body if isinstance(body, dict) else {}

	def raise_for_meta(self, body: dict, path: str):
		meta = body.get("meta") or {}
		if cint(meta.get("code")) < 300:
			return

		errors = meta.get("errors") or []
		detail = (
			", ".join(cstr(error.get("message")) for error in errors) if errors else cstr(meta.get("message"))
		)
		message = f"{meta.get('code')}: {detail}"
		self.log_request(path, error=message)
		frappe.throw(_("AfterShip rejected the request: {0}").format(message))

	def log_request(self, path: str, output=None, error=None):
		# The payload carries the customer's name, address and phone number, so only the endpoint and the
		# outcome are recorded.
		create_request_log(
			{"endpoint": path},
			service_name="AfterShip",
			is_remote_request=True,
			reference_doctype=self.doctype,
			reference_docname=self.name,
			output=output,
			error=error,
			status="Failed" if error else "Completed",
		)

	# --- Contract ------------------------------------------------------------

	def get_rates(self, request: RateRequest) -> list[dict]:
		shipper_accounts = self.get_shipper_account_ids()
		if not shipper_accounts:
			return []

		payload = {
			"async": False,
			"is_document": False,
			"shipper_accounts": [{"id": account} for account in shipper_accounts],
			"shipment": self.build_shipment(
				request.origin, request.destination, request.parcels, request.declared_value
			),
		}
		data = self.request(
			"POST",
			self.get_shipping_base(),
			"/rates",
			payload,
			timeout=min(cint(self.rates_timeout_seconds) or request.timeout_seconds, request.timeout_seconds),
		)
		return [self.build_rate(rate) for rate in data.get("rates") or [] if is_quotable(rate)]

	def get_shipper_account_ids(self) -> list[str]:
		if self.shipper_account_id:
			return [self.shipper_account_id]
		# Rate-shop everything on the key. Cached for the request only; the account list changes rarely but
		# a stale one would quote against an account that has since been removed.
		return [account["id"] for account in self.list_shipper_accounts() if account.get("id")]

	def list_shipper_accounts(self) -> list[dict]:
		data = self.request("GET", self.get_shipping_base(), "/shipper-accounts")
		return data.get("shipper_accounts") or []

	def list_couriers(self) -> list[dict]:
		"""Every courier on this key, with the service types it sells and where it collects from."""
		data = self.request("GET", self.get_shipping_base(), "/couriers")
		return data.get("couriers") or []

	def build_rate(self, rate: dict) -> dict:
		charge = rate.get("total_charge") or {}
		account = rate.get("shipper_account") or {}
		return {
			"service_code": build_service_code(account.get("id"), rate.get("service_type")),
			"service_name": rate.get("service_name") or rate.get("service_type"),
			"carrier": account.get("slug"),
			"amount": flt(charge.get("amount")),
			"currency": charge.get("currency") or self.currency,
			"transit_days": cint(rate.get("transit_time")),
			# AfterShip's rate payload says nothing about cash on delivery, and guessing True here would
			# offer COD on a service that cannot collect it.
			"cod_available": False,
		}

	def create_shipment(self, shipment: dict) -> dict:
		"""Buy a label in one call. A tracking object is then registered and returned as `tracking_ref`;
		a failure there is not fatal."""
		account_id, service_type = split_service_code(shipment.get("service_code"))
		if not (account_id and service_type):
			frappe.throw(_("An AfterShip service code must name both a shipper account and a service type"))

		payload = {
			"async": False,
			"is_document": False,
			"paper_size": "default",
			"service_type": service_type,
			"billing": {"paid_by": "shipper"},
			"shipper_account": {"id": account_id},
			"references": [cstr(shipment.get("order_reference") or shipment.get("reference"))],
			"shipment": self.build_shipment(
				shipment.get("origin"),
				shipment.get("destination"),
				shipment.get("parcels"),
				flt(shipment.get("declared_value")),
			),
		}
		label = self.request("POST", self.get_shipping_base(), "/labels", payload)

		awb = (label.get("tracking_numbers") or [None])[0]
		charge = (label.get("rate") or {}).get("total_charge") or {}
		carrier = ((label.get("shipper_account") or {}).get("slug")) or None
		return {
			"order_ref": label.get("id"),
			"shipment_ref": label.get("id"),
			"awb": awb,
			"carrier": carrier,
			"label_url": ((label.get("files") or {}).get("label") or {}).get("url"),
			"cost_amount": flt(charge.get("amount")),
			"cost_currency": charge.get("currency") or self.currency,
			"status": label.get("status"),
			"tracking_ref": self.register_tracking(awb, carrier, shipment),
		}

	def register_tracking(self, awb: str | None, carrier: str | None, shipment: dict) -> str | None:
		"""Register the AWB with AfterShip Tracking. Never fatal: a key without the separate Tracking
		product gets a permission error, and the label is already paid for."""
		if not (awb and carrier):
			return None

		reference = cstr(shipment.get("order_reference") or shipment.get("reference"))
		try:
			data = self.request(
				"POST",
				self.get_tracking_base(),
				"/trackings",
				{"tracking_number": awb, "slug": carrier, "title": reference, "order_id": reference},
			)
			return (data.get("tracking") or data).get("id")
		except Exception:
			frappe.log_error(
				title="AfterShip tracking registration failed",
				message=f"awb: {awb}, slug: {carrier}",
			)
			return None

	def cancel_shipment(
		self, order_ref: str, shipment_ref: str | None = None, awb: str | None = None
	) -> dict:
		data = self.request(
			"POST",
			self.get_shipping_base(),
			"/cancel-labels",
			{"label": {"id": shipment_ref or order_ref}},
		)
		return {"status": data.get("status") or "Cancelled", "message": data.get("id")}

	def get_tracking(
		self, awb: str, shipment_ref: str | None = None, tracking_ref: str | None = None
	) -> dict:
		if not tracking_ref:
			# Without a registered tracking object there is nothing to read; the label alone carries no
			# carrier scans. Reported as unknown rather than throwing, so a desk sync button just says so.
			return {"status": None, "provider_status": None, "events": []}

		data = self.request("GET", self.get_tracking_base(), f"/trackings/{tracking_ref}")
		tracking = data.get("tracking") or data
		tag = tracking.get("tag")
		return {
			"status": AFTERSHIP_TAG_MAP.get(tag),
			"provider_status": tracking.get("subtag_message") or tag,
			"events": [build_event(checkpoint) for checkpoint in tracking.get("checkpoints") or []],
		}

	def handle_webhook(self, payload: bytes, headers: dict) -> dict:
		"""AfterShip signs its webhooks properly: base64 HMAC-SHA256 of the exact bytes it sent."""
		secret = self.get_password("webhook_secret", raise_exception=False)
		if not secret:
			frappe.throw(_("Webhook secret is not configured in AfterShip Shipping Settings"))

		signature = headers.get(AFTERSHIP_SIGNATURE_HEADER)
		if not signature:
			frappe.throw(_("Missing {0} header").format(AFTERSHIP_SIGNATURE_HEADER))

		# Signed over the raw bytes, so a re-serialised body fails every delivery for no visible reason.
		expected = base64.b64encode(hmac.new(secret.encode(), payload, hashlib.sha256).digest()).decode()
		if not hmac.compare_digest(expected.encode(), signature.encode()):
			frappe.throw(_("AfterShip webhook signature does not match"))

		event = frappe.parse_json(payload.decode())
		message = event.get("msg") or {}
		tag = message.get("tag")
		status = AFTERSHIP_TAG_MAP.get(tag)
		awb = message.get("tracking_number")
		if not (awb and status):
			# Either an event for something we do not track, or a tag deliberately left unmapped.
			return {}

		checkpoints = message.get("checkpoints") or []
		return {
			"awb": cstr(awb),
			"status": status,
			"provider_status": message.get("subtag_message") or tag,
			# AfterShip gives the tracking a stable id and the event a timestamp; together they identify
			# this delivery well enough to recognise a replay.
			"event_id": f"{message.get('id')}:{latest_checkpoint_time(checkpoints)}",
			"events": [build_event(checkpoint) for checkpoint in checkpoints],
		}

	# No pickup, manifest or resume_booking: AfterShip has no such calls and buys labels in one shot.

	# --- Helpers -------------------------------------------------------------

	def build_shipment(
		self, origin: dict | None, destination: dict | None, parcels: list[dict] | None, declared_value: float
	) -> dict:
		return {
			"parcels": [self.build_parcel(parcel, declared_value) for parcel in parcels or []],
			"ship_from": self.build_address(origin or {}),
			"ship_to": self.build_address(destination or {}),
		}

	def build_parcel(self, parcel: dict, declared_value: float) -> dict:
		return {
			"box_type": "custom",
			"weight": {"value": flt(parcel.get("weight")), "unit": "kg"},
			"dimension": {
				"width": flt(parcel.get("width")),
				"height": flt(parcel.get("height")),
				"depth": flt(parcel.get("length")),
				"unit": "cm",
			},
			"items": [self.build_item(item, declared_value) for item in parcel.get("items") or []]
			or [self.build_default_item(declared_value)],
		}

	def build_item(self, item: dict, declared_value: float) -> dict:
		return {
			"description": cstr(item.get("description") or item.get("sku"))[:120],
			"quantity": cint(item.get("quantity")) or 1,
			"price": {"amount": flt(item.get("rate")), "currency": self.currency or "USD"},
			"weight": {"value": flt(item.get("weight")) or 0.5, "unit": "kg"},
			"sku": cstr(item.get("sku")),
		}

	def build_default_item(self, declared_value: float) -> dict:
		"""AfterShip rejects a parcel with no items, so a consignment without line detail still declares one."""
		return {
			"description": "Goods",
			"quantity": 1,
			"price": {"amount": flt(declared_value), "currency": self.currency or "USD"},
			"weight": {"value": 0.5, "unit": "kg"},
			"sku": "GOODS",
		}

	def build_address(self, address: dict) -> dict:
		"""AfterShip rejects empty-string fields outright, so only populated keys are sent."""
		payload = {
			"contact_name": address.get("contact_name"),
			"company_name": address.get("company_name"),
			"street1": address.get("line1"),
			"street2": address.get("line2"),
			"city": address.get("city"),
			"state": address.get("state"),
			"postal_code": address.get("pincode"),
			"country": alpha_3(address.get("country")),
			"phone": address.get("phone"),
			"email": address.get("email"),
			"type": "residential",
		}
		return {key: value for key, value in payload.items() if value not in ("", None)}

	def get_volumetric_divisor(self) -> int:
		return cint(self.volumetric_divisor) or 5000

	@frappe.whitelist()
	def test_connection(self) -> dict:
		"""Prove the key works and name the shipper accounts it can buy against."""
		accounts = self.list_shipper_accounts()
		if not accounts:
			frappe.throw(_("This AfterShip key has no shipper accounts, so no label can be bought."))
		return {
			"shipper_accounts": [
				{
					"id": account.get("id"),
					"slug": account.get("slug"),
					"description": account.get("description"),
				}
				for account in accounts
			]
		}

	@frappe.whitelist()
	def get_service_choices(self) -> dict:
		"""Carrier services this key can sell from the pickup country, for the Shipping Service and
		Delivery Options importers. One group per shipper account."""
		if not self.get_password("api_key", raise_exception=False):
			frappe.throw(_("Set the AfterShip API Key before importing carrier services."))
		if not self.pickup_address:
			frappe.throw(_("Set a Pickup Address before importing carrier services."))

		country = frappe.db.get_value("Address", self.pickup_address, "country")
		if not country:
			frappe.throw(_("Pickup Address {0} has no country set.").format(frappe.bold(self.pickup_address)))

		accounts = self.list_shipper_accounts()
		if self.shipper_account_id:
			# Rates are only ever shopped against the configured account, so a service imported for any
			# other one could never be quoted: it would sit at checkout on its backup charge forever.
			accounts = [account for account in accounts if account.get("id") == self.shipper_account_id]

		return {
			"provider": get_provider_profile(self.doctype),
			"accounts": build_delivery_option_choices(accounts, self.list_couriers(), alpha_3(country)),
		}

	@frappe.whitelist()
	def get_billable_weight(self, parcels: list) -> float:
		return billable_weight(frappe.parse_json(parcels), self.get_volumetric_divisor())


def build_service_code(account_id: str | None, service_type: str | None) -> str:
	return f"{cstr(account_id)}{SERVICE_CODE_SEPARATOR}{cstr(service_type)}"


def split_service_code(service_code: str | None) -> tuple[str | None, str | None]:
	parts = cstr(service_code).split(SERVICE_CODE_SEPARATOR, 1)
	if len(parts) != 2:
		return None, None
	return parts[0] or None, parts[1] or None


def is_quotable(rate: dict) -> bool:
	# The sandbox returns placeholder rows with a null service_type and an error_message; quoting one to a
	# shopper would offer a service that cannot be bought.
	if rate.get("error_message"):
		return False
	return bool(rate.get("service_type")) and flt((rate.get("total_charge") or {}).get("amount")) > 0


def build_event(checkpoint: dict) -> dict:
	location = ", ".join(
		cstr(part)
		for part in (checkpoint.get("city"), checkpoint.get("state"), checkpoint.get("country_name"))
		if part
	)
	return {
		"timestamp": to_system_datetime(checkpoint.get("checkpoint_time") or checkpoint.get("created_at")),
		"status": checkpoint.get("tag"),
		"location": location or checkpoint.get("location"),
		"message": checkpoint.get("message"),
	}


def latest_checkpoint_time(checkpoints: list) -> str:
	if not checkpoints:
		return ""
	latest = checkpoints[-1]
	return cstr(latest.get("checkpoint_time") or latest.get("created_at"))


def alpha_3(country: str | None) -> str | None:
	"""ISO alpha-3 for a Frappe Country name, which AfterShip requires. Uses the Country's alpha-2
	`code`, then pycountry."""
	if not country:
		return None

	code = cstr(frappe.db.get_value("Country", country, "code")).upper()
	try:
		import pycountry

		match = None
		if code:
			match = pycountry.countries.get(alpha_2=code)
		if not match:
			match = pycountry.countries.get(name=country)
		if match:
			return match.alpha_3
	except ImportError:
		pass

	resolved = FALLBACK_ALPHA_3.get(code)
	if not resolved:
		frappe.throw(_("Cannot resolve an ISO alpha-3 country code for {0}").format(frappe.bold(country)))
	return resolved


def origin_can_ship_from(ship_from: str | None, origin: str) -> bool:
	"""AfterShip's courier `ship_from` is one string: "Global", one alpha-3, or a comma list ("HKG,SGP")."""
	ship_from = cstr(ship_from).strip()
	if not ship_from:
		return False
	if ship_from.casefold() == "global":
		return True
	return origin in {code.strip().upper() for code in ship_from.split(",")}


def build_delivery_option_choices(
	shipper_accounts: list[dict], couriers: list[dict], origin: str
) -> list[dict]:
	"""Group each shipper account with its courier's services. Skip accounts whose courier does not
	collect from the origin or lists no service type."""
	couriers_by_slug = {courier.get("slug"): courier for courier in couriers}
	choices = []
	for account in shipper_accounts:
		courier = couriers_by_slug.get(account.get("slug"))
		if not courier or not origin_can_ship_from(courier.get("ship_from"), origin):
			continue

		services = [
			{
				"service_code": build_service_code(account.get("id"), service.get("service_type")),
				"service_name": service.get("service_name") or service.get("service_type"),
			}
			for service in courier.get("courier_service_types") or []
			if service.get("service_type")
		]
		if not services:
			continue

		choices.append(
			{
				"carrier": account.get("slug"),
				"description": account.get("description") or account.get("slug"),
				"services": services,
			}
		)
	return choices


def summarise(body: dict) -> dict:
	"""AfterShip echoes the customer's name, address and phone number, so only ids are logged."""
	data = body.get("data") or {}
	return {key: data[key] for key in ("id", "status", "tracking_numbers") if key in data}
