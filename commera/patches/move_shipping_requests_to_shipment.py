import frappe
from frappe.contacts.doctype.address.address import get_company_address
from frappe.utils.data import getdate

from commera.customizations import create_customizations

OLD_DOCTYPES = ("Shipping Request", "Shipping Parcel")
PARCEL_FIELDS = ("length", "width", "height", "weight", "count")


def execute():
	"""Shipping Request moved to ERPNext's Shipment. The old doctypes are deleted once their rows are copied."""
	if not frappe.db.table_exists("Shipping Request"):
		return
	# after_migrate creates customizations after the patches, so Shipment's custom fields may not exist yet.
	create_customizations()

	for request in frappe.get_all("Shipping Request", fields=["*"], order_by="creation asc"):
		move_request(request)

	for doctype in OLD_DOCTYPES:
		frappe.delete_doc("DocType", doctype, force=True, ignore_missing=True)
		frappe.db.sql_ddl(f"drop table if exists `tab{doctype}`")


def move_request(request):
	"""Inserted without ERPNext's validation: a booked parcel stays on record even when its old row lacks a
	field Shipment requires."""
	shipment = frappe.new_doc("Shipment")
	shipment.update(get_shipment_fields(request))
	shipment.docstatus = get_docstatus(request)
	for parcel in frappe.get_all(
		"Shipping Parcel", {"parent": request.name, "parenttype": "Shipping Request"}, list(PARCEL_FIELDS)
	):
		shipment.append("shipment_parcel", parcel)
	if request.delivery_note:
		shipment.append("shipment_delivery_note", {"delivery_note": request.delivery_note})

	shipment.sync_erpnext_status()
	shipment.status = {0: "Draft", 2: "Cancelled"}.get(shipment.docstatus, shipment.status)
	shipment.set_new_name()
	shipment.set_parent_in_children()
	shipment.db_insert()
	for row in shipment.get_all_children():
		row.db_insert()

	move_tracking_events(request.name, shipment.name)
	move_integration_requests(request.name, shipment.name)


def get_shipment_fields(request) -> dict:
	sales_order = request.ref_docname if request.ref_doctype == "Sales Order" else None
	source = (
		frappe.db.get_value(
			"Sales Order" if sales_order else "Delivery Note",
			sales_order or request.delivery_note or request.ref_docname,
			["customer", "company_address"],
			as_dict=True,
		)
		or frappe._dict()
	)
	return {
		"pickup_from_type": "Company",
		"pickup_company": request.company,
		"pickup_address_name": request.origin_address
		or source.company_address
		or get_company_address(request.company).company_address,
		"delivery_to_type": "Customer",
		"delivery_customer": source.customer,
		"delivery_address_name": request.destination_address,
		"pickup_date": request.pickup_date or getdate(request.creation),
		"description_of_content": request.name,
		"value_of_goods": request.declared_value,
		"shipment_id": request.shipment_ref,
		"shipment_amount": request.cost_amount,
		"awb_number": request.awb,
		"carrier": request.carrier,
		"tracking_url": request.tracking_url,
		"custom_sales_order": sales_order,
		"custom_shipping_provider": request.provider,
		"custom_shipping_service": request.shipping_service,
		"custom_service_code": request.service_code,
		"custom_shipment_status": request.status,
		"custom_provider_status": request.provider_status,
		"custom_currency": request.currency,
		"custom_cod": request.cod,
		"custom_cod_amount": request.cod_amount,
		"custom_cost_currency": request.cost_currency,
		"custom_order_ref": request.order_ref,
		"custom_tracking_ref": request.tracking_ref,
		"custom_pickup_ref": request.pickup_ref,
		"custom_label_url": request.label_url,
		"custom_manifest_url": request.manifest_url,
		"custom_last_webhook_event_id": request.last_webhook_event_id,
		"owner": request.owner,
		"creation": request.creation,
		"modified": request.modified,
		"modified_by": request.modified_by,
	}


def get_docstatus(request) -> int:
	"""A booked or partner-recorded parcel is submitted; an unbooked one stays a draft."""
	if request.status == "Cancelled":
		return 2
	return 1 if request.awb or request.order_ref or not request.provider else 0


def move_tracking_events(request_name: str, shipment_name: str):
	event = frappe.qb.DocType("Shipping Tracking Event")
	(
		frappe.qb.update(event)
		.set(event.parent, shipment_name)
		.set(event.parenttype, "Shipment")
		.set(event.parentfield, "custom_tracking_events")
		.where((event.parent == request_name) & (event.parenttype == "Shipping Request"))
		.run()
	)


def move_integration_requests(request_name: str, shipment_name: str):
	integration_request = frappe.qb.DocType("Integration Request")
	(
		frappe.qb.update(integration_request)
		.set(integration_request.reference_doctype, "Shipment")
		.set(integration_request.reference_docname, shipment_name)
		.where(
			(integration_request.reference_doctype == "Shipping Request")
			& (integration_request.reference_docname == request_name)
		)
		.run()
	)
