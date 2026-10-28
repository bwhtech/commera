from abc import ABC, abstractmethod

# Optional capabilities and the method that implements each. Ask `supports()` rather than
# hard-coding which provider can do what.
OPTIONAL_CAPABILITIES = {
	"booking": "create_shipment",
	"cancel": "cancel_shipment",
	"tracking": "get_tracking",
	"webhook": "handle_webhook",
	"pickup": "schedule_pickup",
	"manifest": "generate_manifest",
	"resume": "resume_booking",
	"service_choices": "get_service_choices",
}


class ShippingProviderBase(ABC):
	"""Contract for a `<Provider> Shipping Settings` Single that backs a Shipping Provider Profile.
	Units are canonical: kg, cm, and major units of the named currency; see `units.normalise_parcel`."""

	@abstractmethod
	def get_rates(
		self,
		origin: dict,
		destination: dict,
		parcels: list[dict],
		cod: bool = False,
		declared_value: float = 0.0,
	) -> list[dict]:
		"""Quote every service that can carry this consignment. Return [] when the provider does not
		serve the route: the caller then prices from the backup charge."""

	def create_shipment(self, shipment: dict) -> dict:
		"""Book one consignment and buy its label. `tracking_ref` is optional: AfterShip tracks on its
		own id, Shiprocket on the AWB."""
		raise NotImplementedError(f"{self.get_provider_name()} cannot book shipments")

	def cancel_shipment(
		self, order_ref: str, shipment_ref: str | None = None, awb: str | None = None
	) -> dict:
		"""Cancel a booked consignment. Return {"status", "message"}."""
		raise NotImplementedError(f"{self.get_provider_name()} cannot cancel shipments")

	def get_tracking(
		self, awb: str, shipment_ref: str | None = None, tracking_ref: str | None = None
	) -> dict:
		"""Read the authoritative status. `status` is one of `status.SHIPMENT_STATUSES`."""
		raise NotImplementedError(f"{self.get_provider_name()} cannot track shipments")

	def handle_webhook(self, payload: bytes, headers: dict) -> dict:
		"""Verify the delivery is really from the provider, then return {} to ignore it, or
		{"awb", "status", "event_id", "events"}."""
		raise NotImplementedError(f"{self.get_provider_name()} sends no webhooks")

	def schedule_pickup(self, shipment_ref: str, pickup_date: str | None = None) -> dict:
		"""Ask the carrier to collect. Return {"pickup_ref", "scheduled_date", "message"}."""
		raise NotImplementedError(f"{self.get_provider_name()} cannot schedule pickups")

	def generate_manifest(self, shipment_refs: list[str]) -> dict:
		"""Return {"manifest_url"} for the handover sheet covering these consignments."""
		raise NotImplementedError(f"{self.get_provider_name()} cannot generate manifests")

	def resume_booking(self, order_ref: str, shipment_ref: str, service_code: str | None = None) -> dict:
		"""Finish a booking that already exists at the provider, returning the `create_shipment` shape.
		Without it a retry creates a second order for one parcel."""
		raise NotImplementedError(f"{self.get_provider_name()} cannot resume a partial booking")

	def get_service_choices(self) -> dict:
		"""Carrier services this account can sell, as {"provider", "accounts"}, for the Shipping Service
		importer. Each `service_code` round-trips into `get_rates` and `create_shipment` unchanged."""
		raise NotImplementedError(f"{self.get_provider_name()} cannot list its carrier services")

	@classmethod
	def supports(cls, capability: str) -> bool:
		"""Whether this provider overrides an optional capability. A classmethod, so a caller can ask
		without loading the settings Single."""
		method_name = OPTIONAL_CAPABILITIES.get(capability)
		if not method_name:
			return False
		return getattr(cls, method_name) is not getattr(ShippingProviderBase, method_name)

	def get_provider_name(self) -> str:
		return self.__class__.__name__
