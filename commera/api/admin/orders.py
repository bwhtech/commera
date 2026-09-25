# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Case, Order
from frappe.query_builder.functions import Count, Max, Sum
from frappe.utils.data import add_days, cint, cstr, flt, formatdate, getdate

from commera.api.admin.catalog import get_unpublishable_options
from commera.api.admin.inventory import get_inventory
from commera.api.shipping import get_order_charge_lines
from commera.utils import get_address_lines

PAGE_LENGTH = 20

# Caps the IN lists the batched lifecycle reads build from a page.
MAX_PAGE_LENGTH = 100

OPEN_STATUSES = ("To Deliver and Bill", "To Deliver", "To Bill")

# Priority order, read top-down: an order is described by the furthest rung it has reached.
STAGE_LABELS = {
	"cancelled": "Cancelled",
	"returned": "Returned",
	"delivered": "Delivered",
	"shipped": "Shipped",
	"fulfilled": "Fulfilled",
	"partly_fulfilled": "Partly fulfilled",
	"packed": "Packed",
	"delivery_note_drafted": "Preparing for shipment",
	"to_fulfil": "To fulfil",
	# An unsubmitted order is waiting on the owner, which is what "Draft" failed to tell them.
	"confirmation_pending": "Confirmation pending",
}

# Sequential timeline, unlike STAGE_LABELS above, which is a priority ordering.
STEP_SEQUENCE = (
	"confirmation_pending",
	"to_fulfil",
	"delivery_note_drafted",
	"packed",
	"shipped",
	"delivered",
)
STEP_POSITIONS = {key: index for index, key in enumerate(STEP_SEQUENCE)}

# Milestone wording, not badge wording; same keys as STAGE_LABELS.
# Shop owners don't know what a Delivery Note is, so the wording stays plain even where the key isn't.
STEP_LABELS = {
	"confirmation_pending": "Confirmation pending",
	"to_fulfil": "Order confirmed",
	"delivery_note_drafted": "Preparing",
	"packed": "Packed",
	"shipped": "Shipped",
	"delivered": "Delivered",
	"cancelled": "Cancelled",
	"returned": "Returned",
}

# Rungs that annotate the dispatch node instead of earning a node of their own.
QUANTITY_STAGES = {"partly_fulfilled": "shipped", "fulfilled": "shipped"}

# These END the path rather than sitting on it.
TERMINAL_STAGES = ("cancelled", "returned")

# Anything unlisted (Draft, Ready To Ship, Cancelled) has not physically moved.
SHIPMENT_STAGES = {
	"Delivered": "delivered",
	"RTO": "returned",
	"Pickup Scheduled": "shipped",
	"In Transit": "shipped",
	"Out For Delivery": "shipped",
	"Undelivered": "shipped",
	"Lost": "shipped",
}

# Rungs where the order no longer waits on the owner; `shipped` is here deliberately.
SETTLED_STAGES = frozenset({"cancelled", "returned", "delivered", "shipped"})

# The carrier statuses that put an order on a settled rung.
SETTLED_SHIPMENT_STATUSES = tuple(
	status for status, stage in SHIPMENT_STAGES.items() if stage in SETTLED_STAGES
)

# How many rows each Home panel shows before it sends the owner to the full screen.
OVERVIEW_PANEL_LENGTH = 5
OVERVIEW_WINDOW_DAYS = 30


@frappe.whitelist()
def get_orders(
	status: str | None = None, search: str | None = None, start: int = 0, page_length: int = PAGE_LENGTH
):
	"""The whole Orders screen in one call."""
	frappe.has_permission("Sales Order", ptype="read", throw=True)

	if status == "open":
		filters = get_open_order_filters()
	elif status == "fulfilled":
		filters = [["docstatus", "<", 2], ["status", "=", "Completed"]]
	elif status == "cancelled":
		filters = [["docstatus", "=", 2]]
	elif status == "unfulfilled":
		filters = get_unfulfilled_order_filters()
	elif status == "unpaid":
		filters = get_unpaid_order_filters()
	elif status == "closed":
		filters = get_closed_order_filters()
	else:
		filters = [["docstatus", "<", 2]]

	# Or-ed against the tab filters above, not appended to them: a plain append would AND the two
	# name matches together and a customer-name hit would never surface a hit on the order name.
	or_filters = (
		[["name", "like", f"%{search}%"], ["customer_name", "like", f"%{search}%"]] if search else None
	)

	if or_filters:
		# frappe.db.count takes no or_filters, so the same filter pair is counted by fetching just
		# the name column for every match — one query either way, just without a page_length cap.
		total = len(frappe.get_all("Sales Order", filters=filters, or_filters=or_filters, pluck="name"))
	else:
		total = frappe.db.count("Sales Order", filters)
	orders = frappe.get_all(
		"Sales Order",
		filters=filters,
		or_filters=or_filters,
		fields=[
			"name",
			"customer",
			"customer_name",
			"transaction_date",
			"status",
			"grand_total",
			"currency",
			"per_delivered",
			"docstatus",
			"custom_ecommerce_payment_mode",
		],
		order_by="creation desc",
		start=cint(start),
		page_length=min(cint(page_length) or PAGE_LENGTH, MAX_PAGE_LENGTH),
	)
	if not orders:
		return {"orders": [], "total": total}

	order_names = [row.name for row in orders]
	item_counts = {}
	for row in frappe.get_all(
		"Sales Order Item",
		filters={"parent": ["in", order_names]},
		fields=["parent", "qty"],
	):
		item_counts[row.parent] = item_counts.get(row.parent, 0) + flt(row.qty)

	lifecycles = read_order_lifecycles(order_names)
	paid_orders = read_paid_orders(order_names)

	return {
		"orders": [
			get_order_row(row, lifecycles.get(cstr(row.name)), paid_orders, item_counts.get(row.name, 0))
			for row in orders
		],
		"total": total,
	}


def get_order_row(order, lifecycle, paid_orders: set, item_count: float) -> dict:
	"""One row of the Orders list."""
	lifecycle = lifecycle or frappe._dict()
	return {
		"name": order.name,
		"customer": order.customer_name or order.customer,
		"placed_on": order.transaction_date,
		"status": order.status,
		"state": describe_state(order, lifecycle),
		"payment_state": describe_payment_state(order, paid_orders),
		"total": flt(order.grand_total),
		"currency": order.currency,
		"item_count": item_count,
		"payment_mode": order.custom_ecommerce_payment_mode,
		"deliveries": lifecycle.get("printable_delivery_notes") or [],
	}


def get_unfulfilled_order_filters() -> list:
	"""Nothing has shipped yet — a confirmation-pending COD draft belongs here too, since delivery
	can only start once an order is submitted, so its per_delivered is 0 the same way."""
	return [["docstatus", "<", 2], ["per_delivered", "=", 0]]


def get_closed_order_filters() -> list:
	"""Cancelled or fully delivered: the two ways an order stops needing attention. Built as the complement
	of "still open" because a filter list can only AND, and as `not in` - `in` hangs on a QueryBuilder."""
	sales_order = frappe.qb.DocType("Sales Order")
	still_open = (
		frappe.qb.from_(sales_order)
		.select(sales_order.name)
		.where(sales_order.docstatus < 2)
		.where(sales_order.status != "Completed")
		.where(sales_order.per_delivered < 100)
	)
	return [["name", "not in", still_open]]


def build_order_invoices_query():
	"""Submitted Sales Invoices joined to the Sales Order they were raised against, nothing selected yet.
	A payment's reference points at the invoice, never the order - so this walks Sales Invoice Item.sales_order."""
	sales_invoice_item = frappe.qb.DocType("Sales Invoice Item")
	sales_invoice = frappe.qb.DocType("Sales Invoice")
	return (
		frappe.qb.from_(sales_invoice_item)
		.join(sales_invoice)
		.on(sales_invoice_item.parent == sales_invoice.name)
		.where(sales_invoice.docstatus == 1)
	)


def read_order_invoices(order_name: str | int) -> list:
	"""Submitted Sales Invoices for one order, newest first; credit notes excluded - the return mapper copies
	`sales_order` onto them too. `creation` is selected: Postgres rejects a DISTINCT ordered by a column it lacks."""
	sales_invoice_item = frappe.qb.DocType("Sales Invoice Item")
	sales_invoice = frappe.qb.DocType("Sales Invoice")
	rows = (
		build_order_invoices_query()
		.select(sales_invoice.name, sales_invoice.creation)
		.distinct()
		.where(sales_invoice_item.sales_order == order_name)
		.where(sales_invoice.is_return == 0)
		.orderby(sales_invoice.creation, order=Order.desc)
	).run(as_dict=True)
	return [cstr(row.name) for row in rows]


def build_paid_orders_query(order_names: list | None = None):
	"""Sales Orders with at least one submitted 'Receive' Payment Entry - the only unambiguous 'paid' signal
	this data model carries. `order_names=None` scopes across every order; a list of names, to one read."""
	sales_invoice_item = frappe.qb.DocType("Sales Invoice Item")
	sales_invoice = frappe.qb.DocType("Sales Invoice")
	payment_entry_reference = frappe.qb.DocType("Payment Entry Reference")
	payment_entry = frappe.qb.DocType("Payment Entry")
	query = (
		build_order_invoices_query()
		.join(payment_entry_reference)
		.on(
			(payment_entry_reference.reference_doctype == "Sales Invoice")
			& (payment_entry_reference.reference_name == sales_invoice.name)
		)
		.join(payment_entry)
		.on(payment_entry_reference.parent == payment_entry.name)
		.select(sales_invoice_item.sales_order.as_("order_name"))
		.distinct()
		.where(payment_entry.docstatus == 1)
		.where(payment_entry.payment_type == "Receive")
	)
	if order_names is not None:
		query = query.where(sales_invoice_item.sales_order.isin(order_names))
	return query


def get_unpaid_order_filters() -> list:
	"""A COD order is settled in cash at the door, outside this paperwork — see the module's COD
	domain note — so only a non-COD order missing its captured payment counts as unpaid here."""
	return [
		["docstatus", "<", 2],
		["custom_ecommerce_payment_mode", "!=", "COD"],
		["name", "not in", build_paid_orders_query()],
	]


def read_paid_orders(order_names: list) -> set:
	"""One batched query for a whole page of orders, not one per row."""
	if not order_names:
		return set()
	rows = build_paid_orders_query(order_names).run(as_dict=True)
	return {cstr(row.order_name) for row in rows}


def describe_payment_state(order, paid_orders: set) -> dict:
	"""The Orders list's payment badge: paid vs pending only. Refund nuance needs per-order Payment
	Entry matching (see describe_payment) that isn't worth batching for a list column."""
	if order.custom_ecommerce_payment_mode == "COD":
		return {"key": "pending", "label": _("Cash on delivery")}
	if cstr(order.name) in paid_orders:
		return {"key": "paid", "label": _("Paid")}
	return {"key": "pending", "label": _("Payment pending")}


def get_open_order_filters() -> list:
	"""Subqueries, not name lists: the stage is derived in Python after the page is fetched, so
	filtering the derived list would corrupt both the page size and the total."""
	filters = [
		["docstatus", "=", 1],
		["status", "in", OPEN_STATUSES],
		["name", "not in", get_returned_orders()],
	]
	from commera.api.shipping import is_connector_installed

	if is_connector_installed():
		filters.append(["name", "not in", get_shipped_orders()])
	return filters


def get_returned_orders():
	"""The orders a submitted return has reversed, as a subquery. A return resets per_delivered, so
	these drift back into an open ERPNext status."""
	delivery_note = frappe.qb.DocType("Delivery Note")
	delivery_note_item = frappe.qb.DocType("Delivery Note Item")
	return (
		frappe.qb.from_(delivery_note_item)
		.join(delivery_note)
		.on(delivery_note_item.parent == delivery_note.name)
		.select(delivery_note_item.against_sales_order)
		.where(delivery_note.docstatus == 1)
		.where(delivery_note.is_return == 1)
		# A NULL anywhere in a NOT IN subquery makes the whole predicate NULL and drops every order.
		.where(delivery_note_item.against_sales_order.notnull())
		.where(delivery_note_item.against_sales_order != "")
	)


def get_shipped_orders():
	"""The orders whose parcel has physically moved, as a subquery. Only the latest shipment counts: a
	rebooked order carries a stale older request that must not settle it."""
	shipping_request = frappe.qb.DocType("Shipping Request")
	newest_moved = Max(
		Case()
		.when(shipping_request.status.isin(SETTLED_SHIPMENT_STATUSES), shipping_request.creation)
		.else_(None)
	)
	return (
		frappe.qb.from_(shipping_request)
		.select(shipping_request.ref_docname)
		.where(shipping_request.ref_doctype == "Sales Order")
		.where(shipping_request.docstatus < 2)
		.where(shipping_request.ref_docname.notnull())
		.where(shipping_request.ref_docname != "")
		.groupby(shipping_request.ref_docname)
		.having(newest_moved == Max(shipping_request.creation))
	)


def describe_state(order, lifecycle=None):
	"""Where this order sits on the fulfilment ladder: a stable key plus the owner-facing label."""
	lifecycle = lifecycle or frappe._dict()
	key = pick_stage(order, lifecycle)
	label = STAGE_LABELS.get(key)
	return {"key": key, "label": _(label) if label else cstr(order.status)}


def pick_stage(order, lifecycle) -> str:
	"""The furthest rung this order has reached, tried from the top of the ladder down."""
	if cint(order.docstatus) == 2:
		return "cancelled"
	if lifecycle.get("stage_from_shipment"):
		return lifecycle.stage_from_shipment
	if lifecycle.get("has_return"):
		return "returned"
	if order.status == "Completed" or flt(order.per_delivered) >= 100:
		return "fulfilled"
	if flt(order.per_delivered) > 0:
		return "partly_fulfilled"
	# Below fulfilment: ERPNext refuses a Packing Slip against anything but a draft Delivery Note.
	if lifecycle.get("has_packing_slip"):
		return "packed"
	if lifecycle.get("has_draft_delivery_note"):
		return "delivery_note_drafted"
	if cint(order.docstatus) == 0:
		return "confirmation_pending"
	if order.status in OPEN_STATUSES:
		return "to_fulfil"
	# On Hold, Closed and friends keep ERPNext's own word rather than a rung they never reached.
	return cstr(order.status)


def describe_progress(order, lifecycle=None) -> list:
	"""The order's walk along the fulfilment path, as the nodes a stepper draws."""
	lifecycle = lifecycle or frappe._dict()
	stage = pick_stage(order, lifecycle)
	timestamps = read_step_timestamps(order, lifecycle)
	reached = furthest_step_reached(order, lifecycle)

	if stage in TERMINAL_STAGES:
		steps = [build_step(key, "done", timestamps) for key in STEP_SEQUENCE[: reached + 1]]
		steps.append(build_step(stage, "current", timestamps))
		return steps

	# A stage with no node of its own borrows the dispatch node, or falls back to the paperwork.
	current = STEP_POSITIONS.get(QUANTITY_STAGES.get(stage, stage), reached)
	note = None if stage in STEP_POSITIONS else STAGE_LABELS.get(stage) or cstr(order.status)

	return [
		build_step(
			key,
			"done" if index < current else "current" if index == current else "upcoming",
			timestamps,
			note=note if index == current else None,
		)
		for index, key in enumerate(STEP_SEQUENCE)
	]


def build_step(key: str, state: str, timestamps: dict, note: str | None = None) -> dict:
	"""One node. `at` is only ever a date a document actually carries, never an inferred one."""
	return {
		"key": key,
		"label": _(STEP_LABELS[key]),
		"state": state,
		"at": timestamps.get(key),
		"note": _(note) if note else None,
	}


def furthest_step_reached(order, lifecycle) -> int:
	"""How far along the sequence the paperwork proves this order got."""
	# A submitted order has cleared confirmation, so its walk starts a rung above a draft's.
	reached = 0 if cint(order.docstatus) == 0 else STEP_POSITIONS["to_fulfil"]
	if lifecycle.get("has_draft_delivery_note") or lifecycle.get("delivery_notes"):
		reached = STEP_POSITIONS["delivery_note_drafted"]
	if lifecycle.get("has_packing_slip"):
		reached = max(reached, STEP_POSITIONS["packed"])
	# A return proves the goods went out before they came back, and it is what reset per_delivered.
	if flt(order.per_delivered) > 0 or lifecycle.get("has_return") or lifecycle.get("dispatched_on"):
		reached = max(reached, STEP_POSITIONS["shipped"])
	if lifecycle.get("stage_from_shipment") in ("shipped", "delivered", "returned"):
		reached = max(reached, STEP_POSITIONS["shipped"])
	# RTO is a parcel that came back without ever arriving, so only an actual delivery scan counts.
	if lifecycle.get("stage_from_shipment") == "delivered":
		reached = max(reached, STEP_POSITIONS["delivered"])
	return reached


def read_step_timestamps(order, lifecycle) -> dict:
	"""When each node happened, from the documents the lifecycle reader already fetched."""
	return {
		"confirmation_pending": order.get("creation"),
		# A draft carries an order date already, but nothing has been confirmed on it yet.
		"to_fulfil": order.transaction_date if cint(order.docstatus) else None,
		"delivery_note_drafted": lifecycle.get("drafted_on"),
		"packed": lifecycle.get("packed_on"),
		"shipped": lifecycle.get("shipped_on") or lifecycle.get("dispatched_on"),
		"delivered": lifecycle.get("delivered_on"),
		# An RTO has no return document, so the carrier's word is the fallback, not the first choice.
		"returned": lifecycle.get("returned_on") or lifecycle.get("carrier_returned_on"),
		# Cancelling is the last thing that can be done to a Sales Order.
		# ponytail: modified stands in for a cancellation timestamp, revisit if a version log is read here
		"cancelled": order.get("modified") if cint(order.docstatus) == 2 else None,
	}


def keep_earliest(lifecycle, field: str, value) -> None:
	"""First of its kind wins: an order split across two delivery notes was drafted when the first
	one was, not when the last one was."""
	if not value:
		return
	current = lifecycle.get(field)
	if current is None or value < current:
		lifecycle[field] = value


def keep_latest(lifecycle, field: str, value) -> None:
	"""Last of its kind wins: an order returned in two parts came back when the last part did."""
	if not value:
		return
	current = lifecycle.get(field)
	if current is None or value > current:
		lifecycle[field] = value


def new_lifecycle():
	"""An order's blank lifecycle, so every reader can append to the lists without a guard."""
	return frappe._dict(delivery_notes=[], printable_delivery_notes=[])


def read_order_lifecycles(order_names: list) -> dict:
	"""Fulfilment paperwork behind a page of orders, keyed by `cstr(name)` - an autoincrement name is an int.
	`delivery_notes` is submitted notes; `printable_delivery_notes` adds drafts but never returns."""
	if not order_names:
		return {}

	lifecycles = {cstr(name): new_lifecycle() for name in order_names}

	delivery_note_links = frappe.get_all(
		"Delivery Note Item",
		filters={"against_sales_order": ["in", order_names], "docstatus": ["<", 2]},
		fields=["parent", "against_sales_order"],
	)
	orders_by_delivery_note = {}
	for row in delivery_note_links:
		orders_by_delivery_note.setdefault(cstr(row.parent), set()).add(cstr(row.against_sales_order))

	delivery_note_names = list(orders_by_delivery_note)
	if delivery_note_names:
		for note in frappe.get_all(
			"Delivery Note",
			filters={"name": ["in", delivery_note_names]},
			fields=["name", "docstatus", "is_return", "creation", "posting_date"],
		):
			for order_name in orders_by_delivery_note.get(cstr(note.name), ()):
				lifecycle = lifecycles.setdefault(order_name, new_lifecycle())
				if not cint(note.is_return):
					lifecycle.printable_delivery_notes.append(cstr(note.name))
				if cint(note.docstatus) == 1:
					lifecycle.delivery_notes.append(cstr(note.name))
					if cint(note.is_return):
						lifecycle.has_return = True
						keep_latest(lifecycle, "returned_on", note.posting_date)
						continue
					keep_earliest(lifecycle, "dispatched_on", note.posting_date)
				else:
					lifecycle.has_draft_delivery_note = True
				# A return note never dates the drafting of the outbound one.
				keep_earliest(lifecycle, "drafted_on", note.creation)

		for slip in frappe.get_all(
			"Packing Slip",
			filters={"delivery_note": ["in", delivery_note_names], "docstatus": ["<", 2]},
			fields=["delivery_note", "creation"],
		):
			for order_name in orders_by_delivery_note.get(cstr(slip.delivery_note), ()):
				lifecycles[order_name].has_packing_slip = True
				keep_earliest(lifecycles[order_name], "packed_on", slip.creation)

	read_shipment_stages(order_names, lifecycles)

	for lifecycle in lifecycles.values():
		lifecycle.delivery_notes = sorted(set(lifecycle.delivery_notes))
		lifecycle.printable_delivery_notes = sorted(set(lifecycle.printable_delivery_notes))
	return lifecycles


def read_shipment_stages(order_names: list, lifecycles: dict) -> None:
	"""Fold each order's latest carrier status into its lifecycle, in one read."""
	from commera.api.shipping import is_connector_installed

	if not is_connector_installed():
		return

	# Newest first, first seen wins: a rebooked order carries a stale request that must not outrank it.
	for request in frappe.get_all(
		"Shipping Request",
		filters={"ref_doctype": "Sales Order", "ref_docname": ["in", order_names], "docstatus": ["<", 2]},
		fields=["ref_docname", "status", "awb", "creation", "modified", "pickup_date"],
		order_by="creation desc",
	):
		lifecycle = lifecycles.get(cstr(request.ref_docname))
		if lifecycle is None or "stage_from_shipment" in lifecycle:
			continue
		stage = SHIPMENT_STAGES.get(cstr(request.status))
		lifecycle.stage_from_shipment = stage
		if stage in ("shipped", "delivered", "returned"):
			# The carrier's pickup date wins over the booking date where the provider gave one.
			keep_earliest(lifecycle, "shipped_on", request.pickup_date or request.creation)
		if stage in ("delivered", "returned"):
			# The request's last write is when it landed on the status it now holds.
			# ponytail: the request's last write stands in for the delivery scan, revisit by reading
			# the Shipping Tracking Event row once the connector records them on this site
			# Kept apart from the return note's posting date: one is a date, the other a datetime.
			field = "delivered_on" if stage == "delivered" else "carrier_returned_on"
			keep_latest(lifecycle, field, request.modified)


def get_order_charges(order):
	charge_lines = get_order_charge_lines(order.name, order.shipping_rule)

	precision = frappe.get_precision("Sales Order", "grand_total", order.currency)
	shipping = flt(charge_lines["shipping"], precision)
	cod_charge = flt(charge_lines["cod_charge"], precision)
	return {
		"shipping": shipping,
		"cod_charge": cod_charge,
		"tax": flt(flt(order.total_taxes_and_charges) - shipping - cod_charge, precision),
	}


@frappe.whitelist()
def get_order(sales_order: str):
	"""Everything one order's screen needs, in one call."""
	frappe.has_permission("Sales Order", doc=sales_order, ptype="read", throw=True)

	order = frappe.db.get_value(
		"Sales Order",
		sales_order,
		[
			"name",
			"customer",
			"customer_name",
			"contact_email",
			"contact_phone",
			"transaction_date",
			"creation",
			"status",
			"docstatus",
			"currency",
			"total",
			"net_total",
			"total_taxes_and_charges",
			"grand_total",
			"shipping_rule",
			"per_delivered",
			"custom_ecommerce_payment_mode",
			"custom_delivery_option",
			"shipping_address",
			"address_display",
			"modified",
		],
		as_dict=True,
	)
	if not order:
		frappe.throw(_("Order {0} not found").format(sales_order))

	items = frappe.get_all(
		"Sales Order Item",
		filters={"parent": sales_order},
		fields=["item_code", "item_name", "qty", "delivered_qty", "rate", "amount", "image"],
		order_by="idx asc",
	)

	# The size lives on the variant's child row, not on the order line.
	sizes_by_item_code = {}
	item_codes = [row.item_code for row in items if row.item_code]
	if item_codes:
		for row in frappe.get_all(
			"Color Size Item",
			filters={"item_code": ["in", item_codes], "parenttype": "Style Attribute Variant"},
			fields=["item_code", "size", "parent"],
		):
			sizes_by_item_code.setdefault(cstr(row.item_code), row.size)

	lifecycle = read_order_lifecycles([order.name]).get(cstr(order.name), frappe._dict())
	state = describe_state(order, lifecycle)
	charges = get_order_charges(order)
	payment_state = describe_payment(order)

	return {
		"name": order.name,
		"customer": order.customer_name or order.customer,
		"customer_id": order.customer,
		"email": order.contact_email,
		"phone": order.contact_phone,
		"placed_on": order.transaction_date,
		"status": order.status,
		"state": state,
		"progress": describe_progress(order, lifecycle),
		"currency": order.currency,
		"total": flt(order.total),
		"net_total": flt(order.net_total),
		"shipping": charges["shipping"],
		# The delivery option the shopper actually chose and paid for. Empty on an order placed
		# before the shipping connector was installed, or one that took the flat Shipping Rule.
		"delivery_option": order.custom_delivery_option,
		"cod_charge": charges["cod_charge"],
		"tax": charges["tax"],
		"total_taxes_and_charges": flt(order.total_taxes_and_charges),
		"grand_total": flt(order.grand_total),
		"payment_mode": order.custom_ecommerce_payment_mode,
		"payment_state": payment_state,
		"shipping_address": get_address_lines(order.address_display),
		"tags": frappe.get_all(
			"Tag Link", filters={"document_type": "Sales Order", "document_name": order.name}, pluck="tag"
		),
		"can_fulfil": can_fulfil_order(order, state),
		"items": [
			{
				"item_code": row.item_code,
				"title": row.item_name,
				"size": sizes_by_item_code.get(cstr(row.item_code)),
				"qty": flt(row.qty),
				"delivered_qty": flt(row.delivered_qty),
				"rate": flt(row.rate),
				"amount": flt(row.amount),
				"image": row.image,
			}
			for row in items
		],
		"deliveries": lifecycle.get("printable_delivery_notes") or [],
		"invoices": read_order_invoices(order.name),
	}


def read_payment_totals(order_name: str) -> tuple[float, float]:
	"""What this order has received and had refunded, off its own Payment Entries. Walks Sales Invoice
	Item.sales_order like build_paid_orders_query: a payment's reference points at the invoice, not the order."""
	sales_invoice_item = frappe.qb.DocType("Sales Invoice Item")
	sales_invoice = frappe.qb.DocType("Sales Invoice")
	payment_entry_reference = frappe.qb.DocType("Payment Entry Reference")
	payment_entry = frappe.qb.DocType("Payment Entry")
	receive_entries = (
		frappe.qb.from_(sales_invoice_item)
		.join(sales_invoice)
		.on(sales_invoice_item.parent == sales_invoice.name)
		.join(payment_entry_reference)
		.on(
			(payment_entry_reference.reference_doctype == "Sales Invoice")
			& (payment_entry_reference.reference_name == sales_invoice.name)
		)
		.join(payment_entry)
		.on(payment_entry_reference.parent == payment_entry.name)
		.select(
			payment_entry.name,
			payment_entry.paid_amount,
			payment_entry.reference_no,
			payment_entry.party,
			payment_entry.party_type,
			payment_entry.company,
		)
		.distinct()
		.where(sales_invoice_item.sales_order == order_name)
		.where(sales_invoice.docstatus == 1)
		.where(payment_entry.docstatus == 1)
		.where(payment_entry.payment_type == "Receive")
	).run(as_dict=True)

	received = sum(flt(row.paid_amount) for row in receive_entries)
	if not receive_entries:
		return received, 0.0

	# Refunds carry no Payment Entry Reference of their own (make_refund_payment_entry adds none) - they are
	# matched back to the receipt by reference_no/party/company, as commera.api.orders.get_refund_status does.
	refunded = 0.0
	for row in receive_entries:
		refunded += sum(
			flt(match.paid_amount)
			for match in frappe.get_all(
				"Payment Entry",
				filters={
					"payment_type": "Pay",
					"docstatus": 1,
					"reference_no": row.reference_no,
					"party_type": row.party_type,
					"party": row.party,
					"company": row.company,
				},
				fields=["paid_amount"],
			)
		)
	return received, refunded


def describe_payment(order) -> dict:
	"""paid | pending | refunded | partially_refunded for one order. Cannot reuse orders.get_refund_status:
	its Payment Entry Reference lookup is keyed on "Sales Order", which never matches a captured payment."""
	if order.custom_ecommerce_payment_mode == "COD":
		return {"key": "pending", "label": _("Cash on delivery")}

	received, refunded = read_payment_totals(order.name)
	if not received:
		return {"key": "pending", "label": _("Payment pending")}
	if refunded >= received:
		return {"key": "refunded", "label": _("Refunded")}
	if refunded > 0:
		return {"key": "partially_refunded", "label": _("Partly refunded")}
	return {"key": "paid", "label": _("Paid")}


def can_fulfil_order(order, state) -> bool:
	"""Whether there is anything left for the owner to ship. per_delivered alone is not the answer: a
	return resets it, so a returned order used to offer a live "Fulfil order" button."""
	return (
		cint(order.docstatus) == 1 and flt(order.per_delivered) < 100 and state["key"] not in SETTLED_STAGES
	)


@frappe.whitelist(methods=["POST"])
def fulfil_order(sales_order: str):
	"""Ship what is still outstanding on an order."""
	# ERPNext moved its mappers to a sibling `mapper` module; both layouts are in the wild.
	try:
		from erpnext.selling.doctype.sales_order.mapper import make_delivery_note
	except ImportError:
		from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	frappe.has_permission("Sales Order", doc=sales_order, ptype="submit", throw=True)
	frappe.has_permission("Delivery Note", ptype="create", throw=True)

	order = frappe.get_doc("Sales Order", sales_order)
	if order.docstatus != 1:
		frappe.throw(_("Only a confirmed order can be fulfilled."))
	if flt(order.per_delivered) >= 100:
		frappe.throw(_("This order has already been fulfilled."))

	# A screen left open on a stale list can still reach here, so enforce and not just hide.
	lifecycle = read_order_lifecycles([order.name]).get(cstr(order.name), frappe._dict())
	state = describe_state(order, lifecycle)
	if state["key"] in SETTLED_STAGES:
		frappe.throw(_("This order is already {0} and needs nothing shipped.").format(state["label"]))

	delivery_note = make_delivery_note(sales_order)
	delivery_note.insert()
	delivery_note.submit()

	return {"delivery_note": delivery_note.name}


@frappe.whitelist()
def get_overview(order_status: str | None = None):
	"""The whole Home screen in one call. `order_status` narrows only the recent-orders panel; the
	figures always describe the whole store."""
	frappe.has_permission("Sales Order", ptype="read", throw=True)
	frappe.has_permission("Item", ptype="read", throw=True)

	today = getdate()
	window_start = add_days(today, -(OVERVIEW_WINDOW_DAYS - 1))
	previous_start = add_days(window_start, -OVERVIEW_WINDOW_DAYS)
	previous_end = add_days(window_start, -1)

	current_window = read_sales_window(window_start, today)
	previous_window = read_sales_window(previous_start, previous_end)

	open_order_filters = get_open_order_filters()
	to_fulfil = frappe.db.count("Sales Order", open_order_filters)
	oldest_open = frappe.db.get_value(
		"Sales Order",
		open_order_filters,
		"transaction_date",
		order_by="transaction_date asc",
	)

	published_now = frappe.db.count("Style Attribute Variant", {"is_published": 1})
	# Nothing records when an option went live, so creation stands in.
	# ponytail: creation date proxies the publish date, revisit if a publish log ever lands
	published_new = frappe.db.count(
		"Style Attribute Variant", {"is_published": 1, "creation": [">=", window_start]}
	)

	# Both panels show five rows while both tiles count the whole store, so the totals travel with the
	# preview: get_inventory already returns the filtered total, and limit=0 counts in the same pass.
	running_low = get_inventory(availability="low", page_length=OVERVIEW_PANEL_LENGTH)
	unpublishable = get_unpublishable_options(limit=0)

	return {
		"currency": get_reporting_currency(),
		"window_days": OVERVIEW_WINDOW_DAYS,
		"stats": [
			{
				"key": "revenue",
				"label": "Revenue",
				"value": flt(current_window.revenue),
				"format": "currency",
				"delta": percent_change(current_window.revenue, previous_window.revenue),
			},
			{
				"key": "orders",
				"label": "Orders",
				"value": cint(current_window.orders),
				"format": "number",
				"delta": percent_change(current_window.orders, previous_window.orders),
			},
			{
				"key": "to_fulfil",
				"label": "Orders to fulfil",
				"value": to_fulfil,
				"format": "number",
				"delta": None,
				"note": _("Oldest waiting since {0}").format(formatdate(oldest_open, "d MMM"))
				if oldest_open
				else _("Nothing waiting"),
			},
			{
				"key": "products_live",
				"label": "Products live",
				"value": published_now,
				"format": "number",
				"delta": percent_change(published_now, published_now - published_new),
			},
		],
		"recent_orders": get_orders(status=order_status, page_length=OVERVIEW_PANEL_LENGTH)["orders"],
		"running_low": running_low["rows"],
		"running_low_total": running_low["total"],
		"needs_attention": unpublishable[:OVERVIEW_PANEL_LENGTH],
		"needs_attention_total": len(unpublishable),
	}


def is_webshop_order(sales_order):
	"""What counts as a sale. Drafts count: a cash-on-delivery order is placed as a draft and is real
	revenue; only a cancelled order is out."""
	return (sales_order.docstatus < 2) & (sales_order.order_type == "Shopping Cart")


def read_sales_window(from_date, to_date):
	"""Revenue and order count for one date window. Sums base_grand_total, not grand_total: only the
	company-currency figure is addable across orders."""
	sales_order = frappe.qb.DocType("Sales Order")
	rows = (
		frappe.qb.from_(sales_order)
		.select(
			Sum(sales_order.base_grand_total).as_("revenue"),
			Count(sales_order.name).as_("orders"),
		)
		.where(is_webshop_order(sales_order))
		.where(sales_order.transaction_date >= from_date)
		.where(sales_order.transaction_date <= to_date)
	).run(as_dict=True)

	return rows[0] if rows else frappe._dict({"revenue": 0, "orders": 0})


def percent_change(current, previous):
	"""Month-over-month change, or None when there is no baseline to compare against."""
	previous = flt(previous)
	if not previous:
		return None
	return flt((flt(current) - previous) / previous * 100, 1)


def get_reporting_currency():
	company = frappe.get_cached_value("Commera Settings", "Commera Settings", "company")
	currency = frappe.get_cached_value("Company", company, "default_currency") if company else None
	return currency or frappe.defaults.get_global_default("currency")


def get_reporting_currency_symbol(currency):
	# Intl carries no narrow symbol for AED or SAR in a Latin locale and falls back to the code, so the
	# symbol has to come from the site's own Currency record.
	return frappe.get_cached_value("Currency", currency, "symbol") if currency else None
