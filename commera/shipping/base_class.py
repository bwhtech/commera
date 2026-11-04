from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from commera.shipping.cache import clear_rates_cache

RATES_TIMEOUT_SECONDS = 10

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
	product: str
	qty: float
	weight: float
	rate: float


@dataclass(frozen=True)
class RateRequest:
	origin: dict
	destination: dict
	parcels: list[dict]
	items: list[RateItem] = field(default_factory=list)
	currency: str = ""
	locale: str = ""
	subtotal: float = 0.0
	total: float = 0.0
	discount: float = 0.0
	customer: str | None = None
	customer_group: str | None = None
	cod: bool = False
	declared_value: float = 0.0
	timeout_seconds: int = RATES_TIMEOUT_SECONDS


class ShippingProviderBase(ABC):
	label: str = ""
	blurb: str = ""
	docs_url: str = ""
	logo: str = ""

	def on_update(self):
		clear_rates_cache()

	@abstractmethod
	def get_rates(self, request: RateRequest) -> list[dict]:
		pass

	def create_shipment(self, shipment: dict) -> dict:
		raise NotImplementedError(f"{self.get_provider_name()} cannot book shipments")

	def cancel_shipment(
		self, order_ref: str, shipment_ref: str | None = None, awb: str | None = None
	) -> dict:
		raise NotImplementedError(f"{self.get_provider_name()} cannot cancel shipments")

	def get_tracking(
		self, awb: str, shipment_ref: str | None = None, tracking_ref: str | None = None
	) -> dict:
		raise NotImplementedError(f"{self.get_provider_name()} cannot track shipments")

	def handle_webhook(self, payload: bytes, headers: dict) -> dict:
		raise NotImplementedError(f"{self.get_provider_name()} sends no webhooks")

	def schedule_pickup(self, shipment_ref: str, pickup_date: str | None = None) -> dict:
		raise NotImplementedError(f"{self.get_provider_name()} cannot schedule pickups")

	def generate_manifest(self, shipment_refs: list[str]) -> dict:
		raise NotImplementedError(f"{self.get_provider_name()} cannot generate manifests")

	def resume_booking(self, order_ref: str, shipment_ref: str, service_code: str | None = None) -> dict:
		raise NotImplementedError(f"{self.get_provider_name()} cannot resume a partial booking")

	def get_service_choices(self) -> dict:
		raise NotImplementedError(f"{self.get_provider_name()} cannot list its carrier services")

	@classmethod
	def supports(cls, capability: str) -> bool:
		method_name = OPTIONAL_CAPABILITIES.get(capability)
		if not method_name:
			return False
		return getattr(cls, method_name) is not getattr(ShippingProviderBase, method_name)

	def get_provider_name(self) -> str:
		return self.label or self.__class__.__name__
