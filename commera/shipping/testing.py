from commera.shipping.base_class import ShippingProviderBase


class InMemoryShippingProvider(ShippingProviderBase):
	"""A carrier that keeps rates, bookings and tracking in memory. Use it with `providers.use_providers`."""

	def __init__(
		self,
		rates: list[dict] | None = None,
		pickup_address: str | None = None,
		volumetric_divisor: int = 0,
		fail_rates: bool = False,
	):
		self.rates = rates or []
		self.pickup_address = pickup_address
		self.volumetric_divisor = volumetric_divisor
		self.fail_rates = fail_rates
		self.rate_requests: list[dict] = []
		self.shipments: dict[str, dict] = {}
		self.cancelled: list[str] = []
		self.tracking: dict[str, dict] = {}

	def get(self, key: str, default=None):
		"""Read a setting the way callers read a settings Single."""
		return getattr(self, key, default)

	def get_rates(
		self,
		origin: dict,
		destination: dict,
		parcels: list[dict],
		cod: bool = False,
		declared_value: float = 0.0,
	) -> list[dict]:
		self.rate_requests.append(
			{"origin": origin, "destination": destination, "parcels": parcels, "cod": cod}
		)
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
