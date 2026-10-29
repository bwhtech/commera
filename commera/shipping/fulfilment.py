import frappe
from erpnext.stock.doctype.shipment.shipment import is_linked_to_party
from frappe import _
from frappe.contacts.doctype.address.address import get_company_address
from frappe.utils.data import cint, cstr, flt, today

from commera.shipping.providers import get_available_shipping_providers, get_provider

# ponytail: one notional box per consignment, since ERPNext parcel templates are optional and most stores
# never fill them in; read a Shipment Parcel Template here once packing rules matter more than a rate.
DEFAULT_PARCEL_DIMENSIONS = {"length": 30.0, "width": 20.0, "height": 10.0}
DEFAULT_ITEM_WEIGHT_KG = 0.5

# Optional custom fields a storefront sets on the Sales Order at checkout. Without them the Shipment
# uses the default provider.
ORDER_CHOICE_FIELDS = ("custom_shipping_provider", "custom_shipping_service_code", "custom_delivery_option")
DESCRIPTION_LENGTH = 140


@frappe.whitelist()
def create_shipment(delivery_note: str) -> str:
	"""Draft a Shipment for a Delivery Note, honouring what the customer paid for."""
	source = frappe.get_doc("Delivery Note", delivery_note)
	source.check_permission("read")

	if existing := get_open_shipment(delivery_note):
		frappe.throw(
			_("Shipment {0} already covers Delivery Note {1}").format(
				frappe.bold(existing), frappe.bold(delivery_note)
			)
		)

	sales_order = get_sales_order(source)
	choice = get_order_choice(sales_order)
	validate_carrier_booking(choice)
	provider = choice.get("provider") or get_default_provider()
	if not provider:
		frappe.throw(_("No shipping provider is enabled, so this delivery cannot be booked."))

	shipment = new_shipment(
		source,
		origin=get_provider_pickup_address(provider) or source.company_address,
		delivery_address=source.shipping_address_name or source.customer_address,
	)
	shipment.update(
		{
			"custom_sales_order": sales_order,
			"custom_shipping_provider": provider,
			"custom_shipping_service": choice.get("delivery_option"),
			"custom_service_code": choice.get("service_code"),
		}
	)
	shipment.append("shipment_delivery_note", {"delivery_note": delivery_note})
	shipment.insert()
	return shipment.name


def new_shipment(source, origin: str | None, delivery_address: str | None):
	"""A draft Shipment from the store to the customer of `source`, a Sales Order or Delivery Note."""
	origin = origin or get_company_address(source.company).company_address
	if not origin:
		frappe.throw(_("Set an address for {0} to ship from.").format(frappe.bold(source.company)))
	link_address_to_company(origin, source.company)

	return frappe.get_doc(
		{
			"doctype": "Shipment",
			"pickup_from_type": "Company",
			"pickup_company": source.company,
			"pickup_address_name": origin,
			"delivery_to_type": "Customer",
			"delivery_customer": source.customer,
			"delivery_address_name": delivery_address,
			"pickup_date": today(),
			"description_of_content": describe_contents(source),
			"value_of_goods": flt(source.base_grand_total),
			"custom_currency": source.currency,
			"shipment_parcel": build_parcels(source),
		}
	)


def link_address_to_company(address: str, company: str):
	"""ERPNext ships only from an address linked to the company. A carrier's pickup address is the store's
	own warehouse, so it is linked on first use."""
	if is_linked_to_party("Address", address, "Company", company):
		return
	address_doc = frappe.get_doc("Address", address)
	address_doc.append("links", {"link_doctype": "Company", "link_name": company})
	address_doc.save(ignore_permissions=True)


def describe_contents(source) -> str:
	names = ", ".join(dict.fromkeys(cstr(row.item_name) for row in source.items))
	return names[:DESCRIPTION_LENGTH] or _("Goods")


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


def get_open_shipment(delivery_note: str) -> str | None:
	"""A second Shipment for the same Delivery Note would buy a second label for one parcel."""
	shipments = frappe.get_all(
		"Shipment",
		filters=[["docstatus", "<", 2], ["Shipment Delivery Note", "delivery_note", "=", delivery_note]],
		pluck="name",
		limit=1,
	)
	return shipments[0] if shipments else None


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


def get_provider_pickup_address(provider: str) -> str | None:
	return get_provider(provider).get("pickup_address")


def build_parcels(delivery_note) -> list[dict]:
	"""One parcel sized from the delivery's own weights, so the carrier is not quoted an empty box."""
	return [{**DEFAULT_PARCEL_DIMENSIONS, "weight": get_delivery_weight(delivery_note), "count": 1}]


def get_delivery_weight(delivery_note) -> float:
	"""Total weight in kg. ERPNext's `total_weight` per row is already qty x unit weight."""
	total = 0.0
	for row in delivery_note.items:
		# A return carries negative quantities, but a physical parcel never weighs less than nothing.
		total += abs(flt(row.total_weight)) or abs(flt(row.qty)) * DEFAULT_ITEM_WEIGHT_KG
	return flt(total, 3) or DEFAULT_ITEM_WEIGHT_KG
