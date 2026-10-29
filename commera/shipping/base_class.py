from abc import ABC, abstractmethod
from dataclasses import dataclass, field

RATES_TIMEOUT_SECONDS = 10

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


@dataclass(frozen=True)
class RateItem:
	item_code: str
	item_name: str
	product: str  # The template of a variant, else the item itself.
	qty: float
	weight: float  # kg for one unit; 0 when the Item has no weight.
	rate: float  # One unit, in the request currency.


@dataclass(frozen=True)
class RateRequest:
	"""What a carrier gets to price one cart. Money is in `currency`, weights in kg."""

	origin: dict
	destination: dict
	parcels: list[dict]
	items: list[RateItem] = field(default_factory=list)
	currency: str = ""
	locale: str = ""
	subtotal: float = 0.0  # Net total of the items.
	total: float = 0.0  # Grand total, after discounts and taxes.
	discount: float = 0.0
	customer: str | None = None
	customer_group: str | None = None
	cod: bool = False
	declared_value: float = 0.0
	# Answer within this, or the rates are dropped and checkout uses backup pricing.
	timeout_seconds: int = RATES_TIMEOUT_SECONDS


class ShippingProviderBase(ABC):
	"""Contract for a `<Provider> Shipping Settings` Single that backs a Shipping Provider Profile.
	Units are canonical: kg, cm, and major units of the named currency; see `units.normalise_parcel`."""

	# Shown on the Integrations screen. `label` also names the carrier's Shipping Provider Profile.
	label: str = ""
	blurb: str = ""
	docs_url: str = ""
	logo: str = ""  # An image URL, such as /assets/<app>/images/<carrier>.svg

	def on_update(self):
		"""Credentials and the pickup address change every quote. A subclass that overrides this calls super()."""
		from commera.shipping.rates import clear_rates_cache  # rates imports this module

		clear_rates_cache()

	@abstractmethod
	def get_rates(self, request: RateRequest) -> list[dict]:
		"""One {"service_code", "service_name", "amount", "currency"} per service, with optional "description",
		"min_delivery_date", "max_delivery_date" and "phone_required". [] when the route is not served."""

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
		return self.label or self.__class__.__name__
