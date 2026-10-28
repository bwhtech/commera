import frappe
from frappe import _
from frappe.utils.data import cint, flt

from commera.shipping.units import DEFAULT_VOLUMETRIC_DIVISOR
from commera.shipping.utils import get_available_shipping_providers, get_default_origin

# ponytail: one notional box per consignment, since ERPNext parcel templates are optional and most stores
# never fill them in; read a Shipment Parcel Template here once packing rules matter more than a rate.
DEFAULT_PARCEL_DIMENSIONS = {"length": 30.0, "width": 20.0, "height": 10.0}
DEFAULT_ITEM_WEIGHT_KG = 0.5

# Optional custom fields a storefront sets on the Sales Order at checkout. Without them the
# Shipping Request uses the default provider.
ORDER_CHOICE_FIELDS = ("custom_shipping_provider", "custom_shipping_service_code", "custom_delivery_option")


@frappe.whitelist()
def create_shipping_request(delivery_note: str) -> str:
	"""Draft a Shipping Request for a Delivery Note, honouring what the customer paid for."""
	source = frappe.get_doc("Delivery Note", delivery_note)
	source.check_permission("read")

	if existing := get_existing_request(delivery_note):
		frappe.throw(
			_("Shipping Request {0} already covers Delivery Note {1}").format(
				frappe.bold(existing), frappe.bold(delivery_note)
			)
		)

	sales_order = get_sales_order(source)
	choice = get_order_choice(sales_order)
	validate_carrier_booking(choice)
	provider = choice.get("provider") or get_default_provider()
	if not provider:
		frappe.throw(_("No shipping provider is enabled, so this delivery cannot be booked."))

	request = frappe.get_doc(
		{
			"doctype": "Shipping Request",
			"provider": provider,
			"shipping_service": choice.get("delivery_option"),
			"service_code": choice.get("service_code"),
			"company": source.company,
			"ref_doctype": "Sales Order" if sales_order else "Delivery Note",
			"ref_docname": sales_order or delivery_note,
			"origin_address": get_origin_address(source, provider),
			"destination_address": source.shipping_address_name or source.customer_address,
			"customer_name": source.customer_name,
			# Sales Order carries contact_phone; Delivery Note only ever had contact_mobile.
			"customer_phone": source.get("contact_phone") or source.contact_mobile,
			"customer_email": source.contact_email,
			"currency": source.currency,
			"declared_value": flt(source.grand_total),
			"parcels": build_parcels(source),
			"delivery_note": delivery_note,
		}
	)
	request.insert()
	return request.name


def validate_carrier_booking(choice: dict):
	"""An option the store delivers itself has no carrier to book, and the default-provider fallback
	would otherwise buy a label the shopper never paid for."""
	delivery_option = choice.get("delivery_option")
	if not delivery_option or choice.get("provider"):
		return
	service = frappe.db.get_value("Shipping Service", delivery_option, ["name", "provider"], as_dict=True)
	if service and not service.provider:
		frappe.throw(
			_("{0} is delivered by the store, so there is no carrier to book.").format(
				frappe.bold(delivery_option)
			)
		)


def get_existing_request(delivery_note: str) -> str | None:
	"""A second Shipping Request for the same Delivery Note would buy a second label for one parcel."""
	return frappe.db.get_value(
		"Shipping Request",
		{"delivery_note": delivery_note, "status": ("!=", "Cancelled")},
		"name",
	)


def get_sales_order(delivery_note) -> str | None:
	for item in delivery_note.items:
		if item.against_sales_order:
			return item.against_sales_order
	return None


def get_order_choice(sales_order: str | None) -> dict:
	"""What the customer chose at checkout. The fields are optional custom fields, hence `has_field`."""
	if not sales_order:
		return {}

	meta = frappe.get_meta("Sales Order")
	fields = [field for field in ORDER_CHOICE_FIELDS if meta.has_field(field)]
	if not fields:
		return {}

	values = frappe.db.get_value("Sales Order", sales_order, fields, as_dict=True) or {}
	return {
		"provider": values.get("custom_shipping_provider"),
		"service_code": values.get("custom_shipping_service_code"),
		"delivery_option": values.get("custom_delivery_option"),
	}


def get_default_provider() -> str | None:
	providers = get_available_shipping_providers()
	return providers[0] if providers else None


def get_origin_address(delivery_note, provider: str) -> str | None:
	"""Ship from the provider's pickup address, else the Delivery Note's company address.
	Carriers that register pickup locations reject any other origin."""
	return get_provider_pickup_address(provider) or delivery_note.company_address


def get_provider_pickup_address(provider: str) -> str | None:
	settings_doctype = frappe.get_cached_value("Shipping Provider Profile", provider, "provider_settings")
	return frappe.get_single(settings_doctype).get("pickup_address")


def build_parcels(delivery_note) -> list[dict]:
	"""One parcel sized from the delivery's own weights, so the carrier is not quoted an empty box."""
	weight = get_delivery_weight(delivery_note)
	return [{**DEFAULT_PARCEL_DIMENSIONS, "weight": weight, "count": 1, "items": build_items(delivery_note)}]


def get_delivery_weight(delivery_note) -> float:
	"""Total weight in kg. ERPNext's `total_weight` per row is already qty x unit weight."""
	total = 0.0
	for row in delivery_note.items:
		# A return carries negative quantities, but a physical parcel never weighs less than nothing.
		total += abs(flt(row.total_weight)) or abs(flt(row.qty)) * DEFAULT_ITEM_WEIGHT_KG
	return flt(total, 3) or DEFAULT_ITEM_WEIGHT_KG


def build_items(delivery_note) -> list[dict]:
	"""Line detail for providers that require it on the consignment (Shiprocket rejects an empty list)."""
	return [
		{
			"description": row.item_name,
			"sku": row.item_code,
			"quantity": cint(abs(flt(row.qty))) or 1,
			"rate": flt(row.rate),
		}
		for row in delivery_note.items
	]


def get_volumetric_divisor(provider: str) -> int:
	settings_doctype = frappe.get_cached_value("Shipping Provider Profile", provider, "provider_settings")
	divisor = cint(frappe.get_single(settings_doctype).get("volumetric_divisor"))
	return divisor or DEFAULT_VOLUMETRIC_DIVISOR
