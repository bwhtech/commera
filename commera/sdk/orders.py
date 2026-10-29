import frappe
from frappe import _
from frappe.utils import create_batch
from frappe.utils.data import cint, cstr, flt

from commera.api.admin.orders import MAX_PAGE_LENGTH, describe_state, read_orders, read_paid_orders
from commera.api.shipping import get_charge_lines, read_order_taxes
from commera.discounts.allocations import get_allocations
from commera.plugin_events import read_shipping_addresses, validate_plugin_fieldnames
from commera.sdk.types import Order
from commera.shipping.fulfilment import get_provider_pickup_address, new_shipment
from commera.shipping.shipment import get_order_shipments
from commera.shipping.status import validate_status

__all__ = ["get_order", "get_orders", "record_shipment"]


def get_order(sales_order: str | int, extra_fields: list[str] | tuple = ()) -> Order:
	"""`extra_fields` reads an app's own Sales Order fields into `plugin_fields`; each must start with the
	name of an installed Commera plugin."""
	frappe.has_permission("Sales Order", doc=sales_order, ptype="read", throw=True)
	validate_plugin_fieldnames("Sales Order", extra_fields)
	orders = read_order_results([sales_order], extra_fields)
	if cstr(sales_order) not in orders:
		frappe.throw(_("Order {0} not found").format(sales_order), frappe.DoesNotExistError)
	return orders[cstr(sales_order)]


def get_orders(sales_orders: list[str | int], extra_fields: list[str] | tuple = ()) -> dict[str, Order]:
	"""Keyed by `cstr(name)`. An order the session user can't read, or that doesn't exist, is left out."""
	frappe.has_permission("Sales Order", ptype="read", throw=True)
	validate_plugin_fieldnames("Sales Order", extra_fields)
	orders = {}
	for order_chunk in create_batch(list(sales_orders), MAX_PAGE_LENGTH):
		readable = frappe.get_list("Sales Order", filters={"name": ["in", order_chunk]}, pluck="name")
		orders.update(read_order_results(readable, extra_fields))
	return orders


def read_order_results(sales_orders: list, extra_fields) -> dict[str, Order]:
	orders = read_orders(sales_orders, extra_fields)
	if not orders:
		return {}
	paid_orders = read_paid_orders([order.name for order in orders.values()])
	taxes_by_order = read_order_taxes(list(orders))
	addresses = read_shipping_addresses(list(orders))
	return {
		name: get_order_result(
			order, paid_orders, taxes_by_order.get(name, []), addresses.get(name), extra_fields
		)
		for name, order in orders.items()
	}


def get_order_result(order, paid_orders: set, taxes: list, shipping_address, extra_fields) -> Order:
	return {
		"name": order.name,
		"customer": order.customer,
		"customer_name": order.customer_name,
		"email": order.contact_email,
		"phone": order.contact_phone,
		"shipping_address": shipping_address,
		"placed_on": order.transaction_date,
		"order_type": order.order_type,
		"currency": order.currency,
		"total": flt(order.total),
		"net_total": flt(order.net_total),
		"grand_total": flt(order.grand_total),
		"rounded_total": flt(order.rounded_total),
		"base_grand_total": flt(order.base_grand_total),
		"base_rounded_total": flt(order.base_rounded_total),
		"payment_mode": order.custom_ecommerce_payment_mode,
		"is_paid": cstr(order.name) in paid_orders,
		"is_cancelled": cint(order.docstatus) == 2,
		"status": order.custom_ecommerce_status,
		"stage": describe_state(order, order.lifecycle),
		"plugin_fees": get_charge_lines(taxes, order.shipping_rule)["plugin_fees"],
		"items": [
			{
				"line_id": line.name,
				"item_code": line.item_code,
				"title": line.item_name,
				"size": line.size,
				"qty": flt(line.qty),
				"delivered_qty": flt(line.delivered_qty),
				"rate": flt(line.rate),
				"amount": flt(line.amount),
				"image": line.image,
				"discount": flt(line.custom_code_discount) * flt(line.qty),
				"attributes": frappe.parse_json(line.custom_line_attributes or "{}"),
			}
			for line in order.lines
		],
		"discounts": get_allocations(order),
		"attributes": frappe.parse_json(order.custom_cart_attributes or "{}"),
		"tags": order.tags,
		"plugin_fields": {fieldname: order.get(fieldname) for fieldname in extra_fields},
	}


def record_shipment(
	sales_order: str | int,
	*,
	awb: str,
	provider: str | None = None,
	carrier: str | None = None,
	status: str = "In Transit",
	events: list[dict] | None = None,
	tracking_url: str | None = None,
) -> str:
	"""Upserts the order's submitted Shipment on `awb`; its status never moves back. No Delivery Note is made.
	Leave `provider` empty when a fulfilment partner shipped it; shoppers see `carrier` and `tracking_url`."""
	validate_status(status)
	if not cstr(awb).strip():
		frappe.throw(_("A shipment needs its AWB."), frappe.ValidationError)
	frappe.has_permission("Sales Order", doc=sales_order, ptype="read", throw=True)

	shipments = get_order_shipments(sales_order, awb_number=awb, docstatus=1)
	if not shipments:
		return create_order_shipment(sales_order, provider, awb, carrier, status, events, tracking_url)

	shipment = frappe.get_doc("Shipment", shipments[0].name)
	shipment.check_permission("write")
	shipment.lock_booking()
	if tracking_url:
		shipment.tracking_url = tracking_url
	if carrier:
		shipment.carrier = carrier
	shipment.apply_status(status, events=events)
	return shipment.name


def create_order_shipment(sales_order, provider, awb, carrier, status, events, tracking_url) -> str:
	if provider and not frappe.db.exists("Shipping Provider Profile", provider):
		frappe.throw(_("Shipping provider {0} does not exist.").format(provider), frappe.ValidationError)

	order = frappe.get_doc("Sales Order", sales_order)
	# The store does not know a partner's warehouse, so a partner parcel ships from the store's address.
	shipment = new_shipment(
		order,
		origin=(provider and get_provider_pickup_address(provider)) or order.company_address,
		delivery_address=order.shipping_address_name or order.customer_address,
	)
	shipment.update(
		{
			"custom_sales_order": order.name,
			"custom_shipping_provider": provider,
			"carrier": carrier,
			"awb_number": awb,
			"tracking_url": tracking_url,
			"custom_shipment_status": status,
		}
	)
	shipment.append_tracking_events(events)
	shipment.insert()
	shipment.submit()
	return shipment.name
