from dataclasses import dataclass
from datetime import datetime

HANDLER_HOOKS = {
	"commera_events": (
		"order_placed",
		"order_paid",
		"order_cancelled",
		"order_refunded",
		"order_fulfilled",
		"order_delivered",
		"order_returned",
		"product_updated",
		"inventory_changed",
	),
	"commera_hooks": ("validate_cart", "cart_fees", "delivery_options", "payment_methods"),
}


@dataclass(frozen=True)
class CommeraEvent:
	"""What a plugin's async commera_events handler receives. Delivery is at least once: dedupe on `id`."""

	id: str
	name: str
	reference_doctype: str
	reference_name: str
	data: dict
	created_at: datetime
