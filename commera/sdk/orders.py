import frappe
from frappe import _
from frappe.utils import create_batch
from frappe.utils.data import cint, cstr, flt

from commera.api.admin.orders import MAX_PAGE_LENGTH, describe_state, read_orders, read_paid_orders
from commera.api.shipping import get_charge_lines, is_connector_installed, read_order_taxes
from commera.app_events import read_shipping_addresses, validate_app_fieldnames
from commera.sdk.types import Order

__all__ = ["ShippingNotInstalled", "get_order", "get_orders", "record_shipment"]


class ShippingNotInstalled(frappe.ValidationError):
	pass


def get_order(sales_order: str | int, extra_fields: list[str] | tuple = ()) -> Order:
	"""`extra_fields` reads an app's own Sales Order fields into `app_fields`; each must start with the
	name of an installed Commera app."""
	frappe.has_permission("Sales Order", doc=sales_order, ptype="read", throw=True)
	validate_app_fieldnames("Sales Order", extra_fields)
	orders = read_order_results([sales_order], extra_fields)
	if cstr(sales_order) not in orders:
		frappe.throw(_("Order {0} not found").format(sales_order), frappe.DoesNotExistError)
	return orders[cstr(sales_order)]


def get_orders(sales_orders: list[str | int], extra_fields: list[str] | tuple = ()) -> dict[str, Order]:
	"""Keyed by `cstr(name)`. An order the session user can't read, or that doesn't exist, is left out."""
	frappe.has_permission("Sales Order", ptype="read", throw=True)
	validate_app_fieldnames("Sales Order", extra_fields)
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
		"app_fees": get_charge_lines(taxes, order.shipping_rule)["app_fees"],
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
			}
			for line in order.lines
		],
		"tags": order.tags,
		"app_fields": {fieldname: order.get(fieldname) for fieldname in extra_fields},
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
	"""Upserts the order's Shipping Request on `awb`; its status never moves back. No Delivery Note is made.
	Leave `provider` empty when a fulfilment partner shipped it; shoppers see `carrier` and `tracking_url`."""
	if not is_connector_installed():
		frappe.throw(_("Install bwh_shipping to record shipments."), ShippingNotInstalled)

	from bwh_shipping.status import validate_status

	validate_status(status)
	if not cstr(awb).strip():
		frappe.throw(_("A shipment needs its AWB."), frappe.ValidationError)
	frappe.has_permission("Sales Order", doc=sales_order, ptype="read", throw=True)

	request_name = frappe.db.get_value(
		"Shipping Request",
		{"ref_doctype": "Sales Order", "ref_docname": cstr(sales_order), "awb": awb},
		"name",
	)
	if not request_name:
		return create_order_shipping_request(
			sales_order, provider, awb, carrier, status, events, tracking_url
		)

	request = frappe.get_doc("Shipping Request", request_name)
	request.check_permission("write")
	request.lock_booking()
	if tracking_url:
		request.tracking_url = tracking_url
	if carrier:
		request.carrier = carrier
	request.apply_status(status, events=events)
	return request.name


def create_order_shipping_request(sales_order, provider, awb, carrier, status, events, tracking_url) -> str:
	"""bwh_shipping's create_shipping_request, fed from the Sales Order instead of a Delivery Note."""
	from bwh_shipping.fulfilment import build_parcels, get_provider_pickup_address

	if provider and not frappe.db.exists("Shipping Provider Profile", provider):
		frappe.throw(_("Shipping provider {0} does not exist.").format(provider), frappe.ValidationError)

	order = frappe.get_doc("Sales Order", sales_order)
	# A partner-made shipment left from the partner's warehouse, which the store does not know.
	origin_address = (get_provider_pickup_address(provider) or order.company_address) if provider else None
	request = frappe.get_doc(
		{
			"doctype": "Shipping Request",
			"provider": provider,
			"carrier": carrier,
			"awb": awb,
			"tracking_url": tracking_url,
			"status": status,
			"company": order.company,
			"ref_doctype": "Sales Order",
			"ref_docname": order.name,
			"origin_address": origin_address,
			"destination_address": order.shipping_address_name or order.customer_address,
			"customer_name": order.customer_name,
			"customer_phone": order.contact_phone,
			"customer_email": order.contact_email,
			"currency": order.currency,
			"declared_value": flt(order.grand_total),
			"parcels": build_parcels(order),
		}
	)
	request.append_tracking_events(events)
	request.insert()
	return request.name
