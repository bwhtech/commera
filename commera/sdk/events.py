from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CommeraEvent:
	"""What an app's async commera_<event> handler receives. Delivery is at least once: dedupe on `id`."""

	id: str
	name: str
	reference_doctype: str
	reference_name: str
	data: dict
	created_at: datetime

	@property
	def sales_order(self) -> str | None:
		return self.reference_name if self.reference_doctype == "Sales Order" else None
