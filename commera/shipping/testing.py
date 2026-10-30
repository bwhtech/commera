import time

import frappe

from commera.shipping.base_class import RateRequest, ShippingProviderBase


class InMemoryShippingProvider(ShippingProviderBase):
	"""A carrier that keeps rates, bookings and tracking in memory. Use it with `providers.use_providers`."""

	def __init__(
		self,
		rates: list[dict] | None = None,
		pickup_address: str | None = None,
		volumetric_divisor: int = 0,
		fail_rates: bool = False,
		delay_seconds: float = 0,
	):
		self.rates = rates or []
		self.pickup_address = pickup_address
		self.volumetric_divisor = volumetric_divisor
		self.fail_rates = fail_rates
		self.delay_seconds = delay_seconds
		self.rate_requests: list[RateRequest] = []
		self.shipments: dict[str, dict] = {}
		self.cancelled: list[str] = []
		self.tracking: dict[str, dict] = {}

	def get(self, key: str, default=None):
		"""Read a setting the way callers read a settings Single."""
		return getattr(self, key, default)

	def get_rates(self, request: RateRequest) -> list[dict]:
		self.rate_requests.append(request)
		time.sleep(self.delay_seconds)
		if self.fail_rates:
			raise ConnectionError("The in-memory carrier is down")
		return [dict(rate) for rate in self.rates]

	def create_shipment(self, shipment: dict) -> dict:
		shipment_ref = f"MEM-{len(self.shipments) + 1}"
		self.shipments[shipment_ref] = shipment
		return {
			"order_ref": shipment_ref,
			"shipment_ref": shipment_ref,
			"awb": f"AWB-{shipment_ref}",
			"carrier": "In-Memory Carrier",
			"status": "Booked",
		}

	def cancel_shipment(
		self, order_ref: str, shipment_ref: str | None = None, awb: str | None = None
	) -> dict:
		self.cancelled.append(order_ref)
		return {"status": "Cancelled", "message": ""}

	def get_tracking(
		self, awb: str, shipment_ref: str | None = None, tracking_ref: str | None = None
	) -> dict:
		return self.tracking.get(awb, {"status": "Booked", "events": []})

	def handle_webhook(self, payload: bytes, headers: dict) -> dict:
		return {}


def insert_shipment_record(sales_order: str, status: str, delivery_note: str | None = None) -> str:
	"""A submitted Shipment row with only the fields order status reads, without ERPNext's validation."""
	shipment = frappe.get_doc(
		{
			"doctype": "Shipment",
			"name": frappe.generate_hash(length=10),
			"docstatus": 1,
			"custom_sales_order": sales_order,
			"custom_shipment_status": status,
		}
	)
	shipment.db_insert()
	if delivery_note:
		shipment.append("shipment_delivery_note", {"delivery_note": delivery_note}).db_insert()
	return shipment.name
