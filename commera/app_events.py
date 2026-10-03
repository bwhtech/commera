from collections import defaultdict

import frappe
from frappe import _
from frappe.permissions import AUTOMATIC_ROLES
from frappe.query_builder import DocType
from frappe.query_builder.functions import Coalesce, Max, Min
from frappe.utils import add_days, add_to_date, create_batch, cstr, flt, now_datetime
from frappe.utils.background_jobs import get_job_status
from pypika.terms import Case, ExistsCriterion
from rq.job import JobStatus

from commera.sdk import API_VERSION, STORE_ORDER_TYPE, as_apps_user
from commera.sdk.events import CommeraEvent

APPS_USER = "commera-apps@commera.local"
RETRY_DELAYS_IN_MINUTES = (1, 5, 30, 120, 360)
# Well past the longest queue timeout, so only a worker that died mid-handler leaves a claim this old.
STALE_CLAIM_MINUTES = 30
LANES_PER_SWEEP = 500
COD_SWEEP_LOOKBACK_DAYS = 30
EXTENDED_DOCTYPES = ("Sales Order", "Quotation", "Sales Invoice", "Item", "Customer")


def fire_event(
	event: str,
	reference_doctype: str,
	reference_name: str | int,
	data: dict | None = None,
	key: str | None = None,
):
	handlers = get_handlers(f"commera_{event}")
	event_key = get_event_key(event, reference_doctype, reference_name, key)
	# Checked first because a duplicate insert also msgprints a red "already exists" at whoever triggered it.
	if frappe.db.exists("Commera Event", event_key):
		return

	if reference_doctype == "Sales Order":
		data = {**get_order_snapshot(reference_name), **(data or {})}

	queued_at = now_datetime()
	try:
		frappe.get_doc(
			{
				"doctype": "Commera Event",
				"event": event,
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"event_key": event_key,
				"data": frappe.as_json(data) if data else None,
				"deliveries": [
					{"app": get_handler_app(handler), "handler": handler, "next_retry_at": queued_at}
					for handler in handlers
				],
			}
		).insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		return

	lane_event = get_lane_event(reference_doctype, event)
	for app in dict.fromkeys(get_handler_app(handler) for handler in handlers):
		enqueue_app_deliveries(app, reference_doctype, reference_name, lane_event)


def get_event_key(event: str, reference_doctype: str, reference_name: str | int, key: str | None) -> str:
	if key is None:
		return f"{reference_name}-{event}"
	if reference_doctype == "Sales Order":
		return f"{reference_name}-{event}-{key}"
	# An item code can be 140 characters on its own, the key's own limit.
	return f"{event}-{key}"


def get_order_snapshot(sales_order: str | int) -> dict:
	order = frappe.db.get_value(
		"Sales Order",
		sales_order,
		["customer", "currency", "grand_total", "custom_ecommerce_payment_mode", "docstatus"],
		as_dict=True,
	)
	return {
		"customer": order.customer,
		"currency": order.currency,
		"grand_total": flt(order.grand_total),
		"payment_mode": order.custom_ecommerce_payment_mode,
		"docstatus": order.docstatus,
	}


def get_lane_event(reference_doctype: str, event: str) -> str | None:
	"""Deliveries run one at a time per lane. An order's events share one lane, so an app hears them in
	order; any other document gets a lane per event, so a failing product handler never holds up stock."""
	return None if reference_doctype == "Sales Order" else event


def get_handler_app(handler: str) -> str:
	return handler.split(".", 1)[0]


def get_handlers(hook: str) -> list[str]:
	return [handler for handler in frappe.get_hooks(hook) if is_supported_app(get_handler_app(handler))]


def is_supported_app(app: str) -> bool:
	api_versions = frappe.get_hooks("commera_api_version", app_name=app)
	return not api_versions or API_VERSION in api_versions


def enqueue_app_deliveries(
	app: str, reference_doctype: str, reference_name: str | int, lane_event: str | None = None
):
	reference_name = cstr(reference_name)
	job_id = f"commera-app-events::{app}::{reference_doctype}::{reference_name}"
	if lane_event:
		job_id = f"{job_id}::{lane_event}"
	# A started job may already be past this event's delivery, so deduplicating against it would drop it.
	lane_job_started = get_job_status(job_id) == JobStatus.STARTED
	frappe.enqueue(
		run_app_deliveries,
		app=app,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		lane_event=lane_event,
		job_id=None if lane_job_started else job_id,
		deduplicate=not lane_job_started,
		enqueue_after_commit=True,
	)


def run_app_deliveries(app: str, reference_doctype: str, reference_name: str, lane_event: str | None = None):
	if app not in frappe.get_installed_apps():
		fail_uninstalled_app_deliveries(app)
		return

	with as_apps_user(app):
		run_lane(app, reference_doctype, reference_name, lane_event)


def fail_uninstalled_app_deliveries(app: str):
	delivery = DocType("Commera Event Delivery")
	(
		frappe.qb.update(delivery)
		.set(delivery.status, "Failed")
		.set(delivery.next_retry_at, None)
		.set(delivery.finished_at, now_datetime())
		.where((delivery.app == app) & (delivery.status.isin(["Queued", "Running"])))
	).run()
	frappe.db.commit()


def run_lane(app: str, reference_doctype: str, reference_name: str, lane_event: str | None = None):
	while delivery := get_next_delivery(app, reference_doctype, reference_name, lane_event):
		if delivery.status == "Running" or (
			delivery.next_retry_at and delivery.next_retry_at > now_datetime()
		):
			return
		# Lost to another job, which now works through the rest of the lane.
		if not claim_delivery(delivery.name):
			return
		if not run_delivery(delivery):
			return


def claim_delivery(delivery_name: str) -> bool:
	"""Committed before the handler runs: a row lock would not survive the handler's own commit."""
	delivery = DocType("Commera Event Delivery")
	(
		frappe.qb.update(delivery)
		.set(delivery.status, "Running")
		.set(delivery.claimed_at, now_datetime())
		.where((delivery.name == delivery_name) & (delivery.status == "Queued"))
	).run()
	claimed = frappe.db._cursor.rowcount == 1
	frappe.db.commit()
	return claimed


def get_next_delivery(app: str, reference_doctype: str, reference_name: str, lane_event: str | None = None):
	delivery = DocType("Commera Event Delivery")
	commera_event = DocType("Commera Event")
	query = (
		frappe.qb.from_(delivery)
		.join(commera_event)
		.on(commera_event.name == delivery.parent)
		.select(
			delivery.name,
			delivery.handler,
			delivery.status,
			delivery.attempts,
			delivery.next_retry_at,
			commera_event.name.as_("event_key"),
			commera_event.event,
			commera_event.reference_doctype,
			commera_event.reference_name,
			commera_event.data,
			commera_event.creation,
		)
		.where(
			(delivery.app == app)
			& delivery.status.isin(("Queued", "Running"))
			& (commera_event.reference_doctype == reference_doctype)
			& (commera_event.reference_name == cstr(reference_name))
		)
		.orderby(commera_event.creation)
		.orderby(delivery.idx)
		.limit(1)
	)
	if lane_event:
		query = query.where(commera_event.event == lane_event)
	deliveries = query.run(as_dict=True)
	return deliveries[0] if deliveries else None


def run_delivery(delivery) -> bool:
	try:
		frappe.get_attr(delivery.handler)(get_commera_event(delivery))
	except Exception:
		frappe.db.rollback()
		error_log = frappe.log_error(
			title=f"commera_{delivery.event} hook failed: {delivery.handler}",
			reference_doctype=delivery.reference_doctype,
			reference_name=delivery.reference_name,
		)
		save_failed_attempt(delivery, error_log.name if error_log else None)
		frappe.db.commit()
		return False

	frappe.db.set_value(
		"Commera Event Delivery",
		delivery.name,
		{
			"status": "Done",
			"attempts": delivery.attempts + 1,
			"finished_at": now_datetime(),
			"next_retry_at": None,
		},
	)
	# Per handler, not a savepoint: a handler may commit on its own, which would release the savepoint.
	frappe.db.commit()
	return True


def get_commera_event(delivery) -> CommeraEvent:
	return CommeraEvent(
		id=delivery.event_key,
		name=delivery.event,
		reference_doctype=delivery.reference_doctype,
		reference_name=delivery.reference_name,
		data=frappe.parse_json(delivery.data) or {},
		created_at=delivery.creation,
	)


def save_failed_attempt(delivery, error_log: str | None):
	attempts = delivery.attempts + 1
	values = {"attempts": attempts, "last_error": error_log}
	if attempts > len(RETRY_DELAYS_IN_MINUTES):
		values.update(status="Failed", next_retry_at=None, finished_at=now_datetime())
	else:
		values.update(
			status="Queued",
			next_retry_at=add_to_date(now_datetime(), minutes=RETRY_DELAYS_IN_MINUTES[attempts - 1]),
		)
	frappe.db.set_value("Commera Event Delivery", delivery.name, values)


def run_due_deliveries():
	release_stale_claims()
	for lane in get_due_lanes():
		enqueue_app_deliveries(lane.app, lane.reference_doctype, lane.reference_name, lane.lane_event or None)


def release_stale_claims():
	"""A claim this old means the worker died mid-handler: count it as a failed attempt."""
	stale_deliveries = frappe.get_all(
		"Commera Event Delivery",
		filters={
			"status": "Running",
			"claimed_at": ["<", add_to_date(now_datetime(), minutes=-STALE_CLAIM_MINUTES)],
		},
		fields=["name", "attempts", "last_error"],
	)
	for stale_delivery in stale_deliveries:
		save_failed_attempt(stale_delivery, stale_delivery.last_error)


def get_due_lanes() -> list:
	"""Only a lane's head ever waits for a retry, so a lane is due once none of its rows waits."""
	delivery = DocType("Commera Event Delivery")
	commera_event = DocType("Commera Event")
	lane_event = Case().when(commera_event.reference_doctype == "Sales Order", "").else_(commera_event.event)
	return (
		frappe.qb.from_(delivery)
		.join(commera_event)
		.on(commera_event.name == delivery.parent)
		.select(
			delivery.app,
			commera_event.reference_doctype,
			commera_event.reference_name,
			lane_event.as_("lane_event"),
		)
		.where(delivery.status == "Queued")
		.groupby(delivery.app, commera_event.reference_doctype, commera_event.reference_name, lane_event)
		.having(Max(Coalesce(delivery.next_retry_at, commera_event.creation)) <= now_datetime())
		.orderby(Min(commera_event.creation))
		.limit(LANES_PER_SWEEP)
		.run(as_dict=True)
	)


@frappe.whitelist(methods=["POST"])
def retry_delivery(delivery: str):
	frappe.only_for("System Manager")
	failed_delivery = frappe.db.get_value(
		"Commera Event Delivery", delivery, ["parent", "app", "status"], as_dict=True
	)
	if not failed_delivery:
		frappe.throw(_("Delivery {0} not found").format(delivery), frappe.DoesNotExistError)
	if failed_delivery.status != "Failed":
		frappe.throw(_("Only a failed delivery can be retried."))

	frappe.db.set_value(
		"Commera Event Delivery",
		delivery,
		{"status": "Queued", "next_retry_at": now_datetime(), "finished_at": None},
	)
	event, reference_doctype, reference_name = frappe.db.get_value(
		"Commera Event", failed_delivery.parent, ["event", "reference_doctype", "reference_name"]
	)
	enqueue_app_deliveries(
		failed_delivery.app, reference_doctype, reference_name, get_lane_event(reference_doctype, event)
	)


def add_apps_user():
	"""The user app handlers run as: every desk role, like Administrator, but its writes are its own."""
	if not frappe.db.exists("User", APPS_USER):
		user = frappe.new_doc("User")
		user.update(
			{
				"email": APPS_USER,
				"first_name": "Commera Apps",
				"user_type": "System User",
				"enabled": 1,
				"send_welcome_email": 0,
			}
		)
		user.insert(ignore_permissions=True)
		# commera.utils.add_roles hands every new user the shopper role.
		user.remove_roles("Customer")

	desk_roles = frappe.get_all(
		"Role",
		filters={"desk_access": 1, "disabled": 0, "name": ["not in", [*AUTOMATIC_ROLES, "Administrator"]]},
		pluck="name",
	)
	missing_roles = set(desk_roles) - set(frappe.get_roles(APPS_USER))
	if missing_roles:
		frappe.get_doc("User", APPS_USER).add_roles(*missing_roles)


def get_settled_cod_orders_query():
	sales_order = DocType("Sales Order")
	unpaid_invoice = DocType("Sales Invoice").as_("unpaid_invoice")
	unpaid_invoice_item = DocType("Sales Invoice Item").as_("unpaid_invoice_item")
	unpaid_invoices = (
		frappe.qb.from_(unpaid_invoice_item)
		.join(unpaid_invoice)
		.on(unpaid_invoice.name == unpaid_invoice_item.parent)
		.select(unpaid_invoice_item.name)
		.where(
			(unpaid_invoice_item.sales_order == sales_order.name)
			& (unpaid_invoice.docstatus == 1)
			& (unpaid_invoice.outstanding_amount > 0)
		)
	)
	return (
		frappe.qb.from_(sales_order)
		.select(sales_order.name)
		.where(
			(sales_order.order_type == STORE_ORDER_TYPE)
			& (sales_order.custom_ecommerce_payment_mode == "COD")
			& (sales_order.docstatus == 1)
			& (sales_order.per_billed >= 100)
			& ExistsCriterion(unpaid_invoices).negate()
		)
	)


def on_payment_entry_submit(doc, method=None):
	"""Only COD orders are paid here: a gateway order fires order_paid at checkout."""
	if doc.payment_type == "Pay":
		fire_order_refunded(doc, get_refunded_orders(doc))
		return
	if doc.payment_type != "Receive":
		return

	invoice_names = [ref.reference_name for ref in doc.references if ref.reference_doctype == "Sales Invoice"]
	if not invoice_names:
		return

	sales_order = DocType("Sales Order")
	sales_invoice_item = DocType("Sales Invoice Item")
	invoiced_orders = (
		frappe.qb.from_(sales_invoice_item)
		.select(sales_invoice_item.sales_order)
		.where(sales_invoice_item.parent.isin(invoice_names))
	)
	paid_orders = get_settled_cod_orders_query().where(sales_order.name.isin(invoiced_orders)).run(pluck=True)
	for order_name in paid_orders:
		fire_event("order_paid", "Sales Order", order_name)


def fire_order_refunded(payment_entry, orders: list):
	"""Each order needs name, currency, conversion_rate and refunded_amount, in the party account's currency."""
	for order in orders:
		fire_event(
			"order_refunded",
			"Sales Order",
			order.name,
			data={
				"payment_entry": payment_entry.name,
				"amount": get_amount_in_order_currency(payment_entry, order),
			},
			key=payment_entry.name,
		)


def get_amount_in_order_currency(payment_entry, order) -> float:
	if payment_entry.party_account_currency == order.currency:
		return flt(order.refunded_amount)
	base_amount = flt(order.refunded_amount) * flt(payment_entry.target_exchange_rate or 1)
	return flt(base_amount / flt(order.conversion_rate or 1))


def get_refunded_orders(payment_entry) -> list:
	"""Store orders a refund pays back: the ones its references point at, each with its own allocation, else
	the ones whose capture shares its reference_no, matched the way get_refund_status matches them."""
	sales_order = DocType("Sales Order")
	order_amounts = get_referenced_order_amounts(payment_entry)
	if order_amounts is not None:
		refunded_orders = sales_order.name.isin(list(order_amounts) or [""])
	else:
		refunded_orders = get_captured_orders(payment_entry, sales_order)
	if refunded_orders is None:
		return []

	orders = (
		frappe.qb.from_(sales_order)
		.select(sales_order.name, sales_order.currency, sales_order.conversion_rate)
		.where(refunded_orders & (sales_order.order_type == STORE_ORDER_TYPE))
		.run(as_dict=True)
	)
	for order in orders:
		order.refunded_amount = (
			order_amounts[order.name] if order_amounts is not None else flt(payment_entry.received_amount)
		)
	return orders


def get_referenced_order_amounts(payment_entry) -> dict | None:
	order_amounts = defaultdict(float)
	invoice_amounts = defaultdict(float)
	for reference in payment_entry.references:
		# A refund against a credit note allocates a negative amount.
		allocated_amount = abs(flt(reference.allocated_amount))
		if reference.reference_doctype == "Sales Order":
			order_amounts[reference.reference_name] += allocated_amount
		elif reference.reference_doctype == "Sales Invoice":
			invoice_amounts[reference.reference_name] += allocated_amount
	if not order_amounts and not invoice_amounts:
		return None

	if invoice_amounts:
		invoiced_orders = frappe.get_all(
			"Sales Invoice Item",
			filters={"parent": ["in", list(invoice_amounts)], "sales_order": ["is", "set"]},
			fields=["parent", "sales_order"],
			distinct=True,
		)
		for invoiced_order in invoiced_orders:
			order_amounts[invoiced_order.sales_order] += invoice_amounts[invoiced_order.parent]
	return order_amounts


def get_captured_orders(payment_entry, sales_order):
	if not payment_entry.reference_no:
		return None

	capture = DocType("Payment Entry")
	capture_reference = DocType("Payment Entry Reference")
	sales_invoice_item = DocType("Sales Invoice Item")
	captured_references = (
		frappe.qb.from_(capture_reference)
		.join(capture)
		.on(capture.name == capture_reference.parent)
		.select(capture_reference.reference_name)
		.where(
			(capture.payment_type == "Receive")
			& (capture.docstatus == 1)
			& (capture.reference_no == payment_entry.reference_no)
			& (capture.party_type == payment_entry.party_type)
			& (capture.party == payment_entry.party)
			& (capture.company == payment_entry.company)
		)
	)
	captured_orders = captured_references.where(capture_reference.reference_doctype == "Sales Order")
	captured_invoices = captured_references.where(capture_reference.reference_doctype == "Sales Invoice")
	invoiced_orders = (
		frappe.qb.from_(sales_invoice_item)
		.select(sales_invoice_item.sales_order)
		.where(sales_invoice_item.parent.isin(captured_invoices))
	)
	return sales_order.name.isin(captured_orders) | sales_order.name.isin(invoiced_orders)


def on_item_update(doc, method=None):
	# A new Item is a product being created or a size being added; the option save that lists it announces it.
	if not doc.flags.in_insert:
		add_changed_products([doc.variant_of or doc.name], "details")


def on_style_attribute_variant_update(doc, method=None):
	if not doc.flags.in_insert:
		add_changed_products(
			[doc.item_style], "published" if doc.has_value_changed("is_published") else "options"
		)


def on_item_price_change(doc, method=None):
	if doc.selling and get_handlers("commera_product_updated"):
		item_template = frappe.db.get_value("Item", doc.item_code, "variant_of") or doc.item_code
		add_changed_products([item_template], "price")


def add_changed_products(item_templates: list[str] | set[str], change: str):
	if not item_templates or not get_handlers("commera_product_updated"):
		return

	changed_products = frappe.local.flags.commera_changed_products
	if changed_products is None:
		changed_products = frappe.local.flags.commera_changed_products = defaultdict(set)
		frappe.db.after_commit.add(enqueue_product_updated)
		frappe.db.after_rollback.add(reset_changed_products)
	for item_template in item_templates:
		if item_template:
			changed_products[cstr(item_template)].add(change)


def reset_changed_products():
	frappe.local.flags.pop("commera_changed_products", None)


def enqueue_product_updated():
	changed_products = frappe.local.flags.pop("commera_changed_products", None) or {}
	for item_code, changes in changed_products.items():
		# No job_id: deduplicating against a queued job would drop this transaction's changes.
		frappe.enqueue(fire_product_updated, item_code=item_code, changed=sorted(changes))


def fire_product_updated(item_code: str, changed: list[str]):
	if not get_handlers("commera_product_updated") or not frappe.db.exists("Item", item_code):
		return
	# An unpublish can take the product off the storefront, and apps still need to hear about it.
	if "published" not in changed and not is_listed_item(item_code):
		return

	fire_event(
		"product_updated",
		"Item",
		item_code,
		data={"item_code": item_code, "changed": changed},
		key=frappe.generate_hash(length=10),
	)


def is_listed_item(item_code: str) -> bool:
	return cstr(item_code) in get_listed_items([item_code])


def get_listed_items(item_codes: list[str]) -> set[str]:
	"""An item is on the storefront when a published Style Attribute Variant sells it or is styled on it."""
	# Imported here: commera.utils imports this module.
	from commera.utils import IN_CLAUSE_CHUNK_SIZE

	style_attribute_variant = DocType("Style Attribute Variant")
	color_size_item = DocType("Color Size Item")
	item_codes = {cstr(item_code) for item_code in item_codes}
	listed_items = set()
	for item_code_chunk in create_batch(list(item_codes), IN_CLAUSE_CHUNK_SIZE):
		rows = (
			frappe.qb.from_(style_attribute_variant)
			.left_join(color_size_item)
			.on(
				(color_size_item.parent == style_attribute_variant.name)
				& (color_size_item.parenttype == "Style Attribute Variant")
			)
			.select(color_size_item.item_code, style_attribute_variant.item_style)
			.distinct()
			.where(
				(style_attribute_variant.is_published == 1)
				& (
					color_size_item.item_code.isin(item_code_chunk)
					| style_attribute_variant.item_style.isin(item_code_chunk)
				)
			)
			.run()
		)
		listed_items.update(cstr(code) for row in rows for code in row if cstr(code) in item_codes)
	return listed_items


def on_stock_ledger_entry_insert(doc, method=None):
	if doc.warehouse == get_ecommerce_warehouse():
		add_changed_items([doc.item_code])


def on_sales_order_stock_reservation(doc, method=None):
	"""Submitting or cancelling an order reserves or releases stock without touching the stock ledger."""
	warehouse = get_ecommerce_warehouse()
	add_changed_items([row.item_code for row in doc.items if row.warehouse == warehouse])


def add_changed_items(item_codes: list[str]):
	if not item_codes or not get_handlers("commera_inventory_changed"):
		return

	changed_items = frappe.local.flags.commera_changed_items
	if changed_items is None:
		# One job per item per transaction: deduplicate only sees jobs already in the queue.
		changed_items = frappe.local.flags.commera_changed_items = set()
		frappe.db.after_commit.add(enqueue_inventory_changed)
		frappe.db.after_rollback.add(reset_changed_items)
	changed_items.update(item_codes)


def get_ecommerce_warehouse() -> str | None:
	return frappe.get_cached_value("Commera Settings", "Commera Settings", "ecommerce_warehouse")


def reset_changed_items():
	frappe.local.flags.pop("commera_changed_items", None)


def enqueue_inventory_changed():
	for item_code in frappe.local.flags.pop("commera_changed_items", None) or ():
		frappe.enqueue(
			fire_inventory_changed,
			item_code=item_code,
			job_id=f"commera-inventory::{item_code}",
			deduplicate=True,
		)


def fire_inventory_changed(item_code: str):
	# Imported here: commera.utils imports this module.
	from commera.utils import get_available_stock

	if not get_handlers("commera_inventory_changed") or not is_listed_item(item_code):
		return

	warehouse = get_ecommerce_warehouse()
	actual_qty = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty")
	fire_event(
		"inventory_changed",
		"Item",
		item_code,
		data={
			"warehouse": warehouse,
			"actual_qty": flt(actual_qty),
			"available_qty": get_available_stock(item_code, warehouse)["stock_qty"],
		},
		key=frappe.generate_hash(length=10),
	)


def sweep_missed_cod_payments():
	sales_order = DocType("Sales Order")
	commera_event = DocType("Commera Event")
	paid_event = (
		frappe.qb.from_(commera_event)
		.select(commera_event.name)
		.where(
			(commera_event.reference_doctype == "Sales Order")
			& (commera_event.reference_name == sales_order.name)
			& (commera_event.event == "order_paid")
		)
	)
	missed_orders = (
		get_settled_cod_orders_query()
		.where(sales_order.modified >= add_days(now_datetime(), -COD_SWEEP_LOOKBACK_DAYS))
		.where(ExistsCriterion(paid_event).negate())
		.run(pluck=True)
	)
	for order_name in missed_orders:
		fire_event("order_paid", "Sales Order", order_name)


def on_sales_order_cancel(doc, method=None):
	if doc.get("order_type") == STORE_ORDER_TYPE:
		fire_event("order_cancelled", "Sales Order", doc.name)


def validate_extension_apps():
	extension_apps = get_extension_apps()
	for app in extension_apps:
		api_versions = frappe.get_hooks("commera_api_version", app_name=app)
		if not api_versions:
			print(f"{app} doesn't declare commera_api_version, so Commera can't tell if its hooks still fit.")
		elif API_VERSION not in api_versions:
			message = f"{app} supports Commera API versions {api_versions}, not {API_VERSION}: its hooks are skipped."
			print(message)
			frappe.log_error(title=f"{app} does not support this Commera", message=message)

	if unprefixed_fields := get_unprefixed_custom_fields(extension_apps):
		message = (
			"Custom Fields should start with their app's name, so two apps never claim one column:\n"
			+ ("\n".join(f"{field.dt}.{field.fieldname} ({field.app_name})" for field in unprefixed_fields))
		)
		print(message)
		frappe.log_error(title="Commera apps added unprefixed Custom Fields", message=message)


def get_extension_apps() -> list[str]:
	return [
		app
		for app in frappe.get_installed_apps()
		if app != "commera" and any(hook.startswith("commera_") for hook in frappe.get_hooks(app_name=app))
	]


def get_unprefixed_custom_fields(apps: list[str]) -> list:
	if not apps:
		return []

	custom_field = DocType("Custom Field")
	module_def = DocType("Module Def")
	custom_fields = (
		frappe.qb.from_(custom_field)
		.join(module_def)
		.on(module_def.name == custom_field.module)
		.select(custom_field.dt, custom_field.fieldname, module_def.app_name)
		.where(custom_field.dt.isin(EXTENDED_DOCTYPES) & module_def.app_name.isin(apps))
		.orderby(custom_field.dt)
		.orderby(custom_field.fieldname)
		.run(as_dict=True)
	)
	return [field for field in custom_fields if not field.fieldname.startswith(f"{field.app_name}_")]


def get_app_fieldnames(doctype: str) -> list[str]:
	"""The columns on `doctype` named `<app>_...` after an installed Commera app."""
	prefixes = tuple(f"{app}_" for app in get_extension_apps())
	if not prefixes:
		return []
	return [
		fieldname
		for fieldname in frappe.get_meta(doctype).get_valid_columns()
		if fieldname.startswith(prefixes)
	]


def validate_app_fieldnames(doctype: str, fieldnames) -> None:
	if not_app_fields := {cstr(fieldname) for fieldname in fieldnames} - set(get_app_fieldnames(doctype)):
		frappe.throw(
			_("{0} is not a field an installed Commera app owns on {1}.").format(
				", ".join(sorted(not_app_fields)), _(doctype)
			),
			frappe.ValidationError,
		)
