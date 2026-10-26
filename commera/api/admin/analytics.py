# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

"""Analytics Settings read/write (System Manager only), plus the Revenue/Inventory/Storefront reports.
The reports reuse analytics_dashboard's session/conversion and is_webshop_order (drafts count) definitions."""

import frappe
from frappe.query_builder import Order
from frappe.query_builder.functions import Coalesce, Count, DateFormat, Max, NullIf, Sum
from frappe.utils.data import (
	add_days,
	add_months,
	cint,
	cstr,
	date_diff,
	flt,
	formatdate,
	get_first_day,
	getdate,
)

from commera.api.admin.catalog import get_default_rates, get_item_templates_by_item_code
from commera.api.admin.settings import coerce_field_value
from commera.api.analytics_dashboard import (
	get_funnel,
	get_landing_pages,
	get_period_kpis,
	get_previous_window,
	get_rate,
	get_stock_movement,
	get_window,
	in_window,
	is_provider_configured,
)
from commera.discounts.allocations import get_allocations
from commera.utils import get_store_currency

ANALYTICS_SETTINGS_DOCTYPE = "Analytics Settings"

PLAIN_FIELDS = (
	"enable_first_party",
	"enable_ga4",
	"ga4_measurement_id",
	"ga4_property_id",
	"enable_facebook",
	"fb_pixel_id",
)

# Never leave the server. The client only ever learns whether each one holds a value.
SECRET_FIELDS = ("ga4_service_account_json", "fb_access_token")

SCRIPT_FIELDS = ("title", "enabled", "script")

TOP_DISCOUNTS_LIMIT = 5


def get_analytics_settings_doc():
	frappe.only_for("System Manager")
	return frappe.get_cached_doc(ANALYTICS_SETTINGS_DOCTYPE)


def format_custom_tracking_scripts(settings):
	return [
		{fieldname: row.get(fieldname) for fieldname in SCRIPT_FIELDS}
		for row in settings.custom_tracking_scripts
	]


@frappe.whitelist()
def get_analytics_settings():
	"""Everything the Analytics tab renders. Secrets are reported as set/not-set, never returned."""
	settings = get_analytics_settings_doc()

	data = {fieldname: settings.get(fieldname) for fieldname in PLAIN_FIELDS}
	for fieldname in SECRET_FIELDS:
		data[f"{fieldname}_is_set"] = bool(settings.get_password(fieldname, raise_exception=False))

	data["ga4_configured"] = is_provider_configured("ga4", settings)
	data["meta_configured"] = is_provider_configured("meta", settings)
	data["custom_tracking_scripts"] = format_custom_tracking_scripts(settings)
	return data


def apply_secret_values(settings, values, cleared_fieldnames):
	# A blank secret keeps the stored one: save_passwords() recognises Frappe's mask.
	for fieldname in SECRET_FIELDS:
		if fieldname in cleared_fieldnames:
			settings.set(fieldname, "")
			continue
		new_secret = cstr(values.get(fieldname) or "").strip()
		if new_secret:
			settings.set(fieldname, new_secret)


def apply_custom_tracking_scripts(settings, rows):
	settings.set("custom_tracking_scripts", [])
	for row in rows:
		title = cstr(row.get("title") or "").strip()
		script = cstr(row.get("script") or "").strip()
		if not title or not script:
			frappe.throw(frappe._("Every tracking script needs a title and a snippet"))
		settings.append(
			"custom_tracking_scripts",
			{"title": title, "enabled": cint(row.get("enabled")), "script": script},
		)


@frappe.whitelist(methods=["POST"])
def save_analytics_settings(**kwargs):
	frappe.only_for("System Manager")

	meta = frappe.get_meta(ANALYTICS_SETTINGS_DOCTYPE)
	settings = frappe.get_doc(ANALYTICS_SETTINGS_DOCTYPE)

	for fieldname in PLAIN_FIELDS:
		if fieldname not in kwargs:
			continue
		docfield = meta.get_field(fieldname)
		settings.set(fieldname, coerce_field_value(docfield.fieldtype, kwargs[fieldname]))

	cleared_fieldnames = set(frappe.parse_json(kwargs.get("cleared_secrets") or "[]"))
	unknown_secrets = cleared_fieldnames - set(SECRET_FIELDS)
	if unknown_secrets:
		frappe.throw(frappe._("Not an analytics secret: {0}").format(", ".join(sorted(unknown_secrets))))
	apply_secret_values(settings, kwargs, cleared_fieldnames)

	if "custom_tracking_scripts" in kwargs:
		apply_custom_tracking_scripts(settings, frappe.parse_json(kwargs["custom_tracking_scripts"]) or [])

	settings.save()
	frappe.clear_document_cache(ANALYTICS_SETTINGS_DOCTYPE)
	return get_analytics_settings()


# Report screens: /analytics/revenue, /analytics/inventory, /analytics/storefront
# ---------------------------------------------------------------------------

REPORT_MONTHS_DEFAULT = 12
INVENTORY_VELOCITY_LIMIT = 6
DEAD_STOCK_LIMIT = 6
TOP_PAGES_LIMIT = 5

# The report header's own range dropdown, mapped to a trailing month count. Charts stay month-bucketed
# at every range, so a 7/30-day window renders one or two bars.
RANGE_MONTHS = {"Last 7 days": 1, "Last 30 days": 1, "Last 12 months": 12, "All time": 36}


def month_key(date_value):
	return getdate(date_value).strftime("%Y-%m")


def month_window(months):
	"""The trailing N calendar months, inclusive of the current one."""
	months = cint(months) or REPORT_MONTHS_DEFAULT
	today = getdate()
	start = get_first_day(add_months(today, -(months - 1)))
	return start, today, months


def build_month_buckets(start, today):
	buckets = {}
	month = start
	while month <= today:
		buckets[month.strftime("%Y-%m")] = month
		month = add_months(month, 1)
	return buckets


def get_refund_totals_by_order(order_names):
	"""Sum of 'Pay' (refund) Payment Entries per order, batched for a whole reporting window in one query.
	A Payment Entry Reference points at the invoice, never the order - same hop as build_paid_orders_query."""
	if not order_names:
		return {}

	sales_invoice_item = frappe.qb.DocType("Sales Invoice Item")
	invoice_rows = (
		frappe.qb.from_(sales_invoice_item)
		.select(sales_invoice_item.sales_order, sales_invoice_item.parent)
		.distinct()
		.where(sales_invoice_item.sales_order.isin(order_names))
		.run()
	)
	if not invoice_rows:
		return {}
	order_by_invoice = {invoice: order for order, invoice in invoice_rows}

	sales_invoice = frappe.qb.DocType("Sales Invoice")
	payment_entry_reference = frappe.qb.DocType("Payment Entry Reference")
	payment_entry = frappe.qb.DocType("Payment Entry")
	refund_rows = (
		frappe.qb.from_(payment_entry_reference)
		.join(payment_entry)
		.on(payment_entry_reference.parent == payment_entry.name)
		.join(sales_invoice)
		.on(
			(payment_entry_reference.reference_doctype == "Sales Invoice")
			& (payment_entry_reference.reference_name == sales_invoice.name)
		)
		.select(sales_invoice.name, Sum(payment_entry_reference.allocated_amount))
		.where(sales_invoice.name.isin(list(order_by_invoice)))
		.where(sales_invoice.docstatus == 1)
		.where(payment_entry.docstatus == 1)
		.where(payment_entry.payment_type == "Pay")
		.groupby(sales_invoice.name)
		.run()
	)

	totals = {}
	for invoice_name, amount in refund_rows:
		order_name = order_by_invoice.get(invoice_name)
		if order_name:
			totals[order_name] = totals.get(order_name, 0.0) + flt(amount)
	return totals


def read_window_totals(from_date, to_date):
	"""Revenue/orders/refunds for a plain date window - the "previous period" half of the Revenue report's
	comparison, kept out of the monthly series so the series carries no throwaway extra bucket."""
	from commera.api.admin.orders import is_webshop_order

	sales_order = frappe.qb.DocType("Sales Order")
	rows = (
		frappe.qb.from_(sales_order)
		.select(sales_order.name, sales_order.base_grand_total)
		.where(is_webshop_order(sales_order))
		.where(sales_order.transaction_date >= from_date)
		.where(sales_order.transaction_date <= to_date)
		.run(as_dict=True)
	)
	refunds_by_order = get_refund_totals_by_order([row.name for row in rows])
	revenue = sum(flt(row.base_grand_total) for row in rows)
	refunds = sum(flt(refunds_by_order.get(row.name, 0)) for row in rows)
	return {"revenue": revenue, "orders": len(rows), "refunds": refunds}


@frappe.whitelist()
def get_revenue_report(months: int = REPORT_MONTHS_DEFAULT):
	"""Monthly revenue/orders/discounts/refunds for the trailing N months, plus a vs-previous comparison.
	Reuses orders.is_webshop_order, so drafts count as real sales here as on the Home screen and Orders list."""
	frappe.only_for("System Manager")
	from commera.api.admin.orders import is_webshop_order

	start, today, months = month_window(months)
	buckets = build_month_buckets(start, today)

	sales_order = frappe.qb.DocType("Sales Order")
	order_rows = (
		frappe.qb.from_(sales_order)
		.select(
			sales_order.name,
			sales_order.transaction_date,
			sales_order.base_grand_total,
			sales_order.base_discount_amount,
			sales_order.conversion_rate,
			sales_order.custom_discount_allocations,
		)
		.where(is_webshop_order(sales_order))
		.where(sales_order.transaction_date >= start)
		.run(as_dict=True)
	)
	refunds_by_order = get_refund_totals_by_order([row.name for row in order_rows])

	series_by_month = {
		key: {"revenue": 0.0, "orders": 0, "discounts": 0.0, "refunds": 0.0} for key in buckets
	}
	for row in order_rows:
		key = month_key(row.transaction_date)
		bucket = series_by_month.setdefault(
			key, {"revenue": 0.0, "orders": 0, "discounts": 0.0, "refunds": 0.0}
		)
		bucket["revenue"] += flt(row.base_grand_total)
		bucket["orders"] += 1
		bucket["discounts"] += get_base_discount_given(row)
		bucket["refunds"] += flt(refunds_by_order.get(row.name, 0))

	series = []
	for key in sorted(series_by_month):
		bucket = series_by_month[key]
		revenue, orders = bucket["revenue"], bucket["orders"]
		series.append(
			{
				"month": key,
				"label": formatdate(f"{key}-01", "MMM"),
				"revenue": revenue,
				"orders": orders,
				"aov": round(revenue / orders, 2) if orders else 0.0,
				"discounts": bucket["discounts"],
				"refunds": bucket["refunds"],
			}
		)

	total_revenue = sum(row["revenue"] for row in series)
	total_orders = sum(row["orders"] for row in series)
	total_refunds = sum(row["refunds"] for row in series)

	previous_start = add_months(start, -months)
	previous_end = add_days(start, -1)
	previous = read_window_totals(previous_start, previous_end)

	return {
		"currency": get_store_currency(),
		"months": series,
		"stats": {
			"revenue": {"value": total_revenue, "previous": previous["revenue"]},
			"orders": {"value": total_orders, "previous": previous["orders"]},
			"aov": {
				"value": round(total_revenue / total_orders, 2) if total_orders else 0.0,
				"previous": round(previous["revenue"] / previous["orders"], 2) if previous["orders"] else 0.0,
			},
			"refunds": {"value": total_refunds, "previous": previous["refunds"]},
		},
		"discounts": get_discount_summary(order_rows),
	}


def get_discount_summary(order_rows) -> dict:
	given, orders, by_label = 0.0, 0, {}
	for row in order_rows:
		allocations = get_allocations(row)
		if not allocations:
			continue
		orders += 1
		labels_on_order = set()
		for allocation in allocations:
			amount = get_base_allocation_amount(row, allocation)
			label = allocation.get("code") or allocation.get("title")
			given += amount
			entry = by_label.setdefault(label, {"label": label, "given": 0.0, "orders": 0})
			entry["given"] += amount
			if label not in labels_on_order:
				entry["orders"] += 1
				labels_on_order.add(label)
	top = sorted(by_label.values(), key=lambda entry: entry["given"], reverse=True)[:TOP_DISCOUNTS_LIMIT]
	return {
		"given": flt(given, 2),
		"orders": orders,
		"top": [{**entry, "given": flt(entry["given"], 2)} for entry in top],
	}


def get_base_discount_given(row) -> float:
	# Codes, plus what ERPNext gave on its own (a Pricing Rule, staff's Additional Discount) beyond the order code.
	allocations = get_allocations(row)
	codes = sum(get_base_allocation_amount(row, allocation) for allocation in allocations)
	order_codes = sum(
		get_base_allocation_amount(row, allocation)
		for allocation in allocations
		if allocation.get("discount_class") == "Order"
	)
	return codes + max(flt(row.base_discount_amount) - order_codes, 0)


def get_base_allocation_amount(row, allocation: dict) -> float:
	return flt(allocation.get("amount")) * (flt(row.conversion_rate) or 1)


def get_item_sales(from_date, to_date, item_codes):
	"""units/revenue/last-sold per sellable size, one aggregate query regardless of scope. from_date=None
	scans the size's whole history ("last sold, ever"); drafts count - see is_webshop_order."""
	if not item_codes:
		return {}
	from commera.api.admin.orders import is_webshop_order

	sales_order = frappe.qb.DocType("Sales Order")
	sales_order_item = frappe.qb.DocType("Sales Order Item")
	query = (
		frappe.qb.from_(sales_order_item)
		.join(sales_order)
		.on(sales_order.name == sales_order_item.parent)
		.select(
			sales_order_item.item_code,
			Sum(sales_order_item.qty),
			Sum(sales_order_item.base_amount),
			Max(sales_order.transaction_date),
		)
		.where(is_webshop_order(sales_order))
		.where(sales_order_item.item_code.isin(item_codes))
		.groupby(sales_order_item.item_code)
	)
	if from_date:
		query = query.where(sales_order.transaction_date >= from_date)
	if to_date:
		query = query.where(sales_order.transaction_date <= to_date)
	rows = query.run()
	return {row[0]: {"units": cint(row[1]), "revenue": flt(row[2]), "last_sold": row[3]} for row in rows}


@frappe.whitelist()
def get_inventory_report(months: int = REPORT_MONTHS_DEFAULT):
	"""Stock value and sell-through for the shop's own ecommerce warehouse. "Value" prices on-hand stock at
	today's selling price - "what my shelves are worth to sell", not ERPNext's landed-cost valuation."""
	frappe.only_for("System Manager")
	from commera.api.admin.inventory import get_inventory

	start, today, months = month_window(months)

	rows = get_inventory(page_length=100000)["rows"]
	item_codes = [row["item_code"] for row in rows]
	rates = get_default_rates(item_codes)
	stock_value_now = sum(flt(row["stock"]) * rates.get(row["item_code"], 0) for row in rows)
	units_on_hand_now = sum(flt(row["stock"]) for row in rows)
	avg_price = stock_value_now / units_on_hand_now if units_on_hand_now else 0.0

	window_start_30d = add_days(today, -29)
	sales_30d = get_item_sales(window_start_30d, today, item_codes)
	sales_lifetime = get_item_sales(None, today, item_codes)
	units_sold_30d = sum(row["units"] for row in sales_30d.values())

	templates_by_item_code = get_item_templates_by_item_code(item_codes)

	stock_by_template, units_30d_by_template, titles_by_template = {}, {}, {}
	for row in rows:
		template = templates_by_item_code.get(row["item_code"])
		if not template:
			continue
		stock_by_template[template] = stock_by_template.get(template, 0) + flt(row["stock"])
		units_30d_by_template[template] = units_30d_by_template.get(template, 0) + sales_30d.get(
			row["item_code"], {}
		).get("units", 0)
		titles_by_template.setdefault(template, row["product"])

	velocity = []
	for template, stock in stock_by_template.items():
		sold = units_30d_by_template.get(template, 0)
		velocity.append(
			{
				"product": titles_by_template.get(template, template),
				"rate": get_rate(sold, sold + stock),
				# Undefined, not zero, when nothing has sold in the window - a bar chart with no
				# real cover figure should read as a gap, not "covered forever".
				"days": round(stock / (sold / 30), 1) if sold else None,
			}
		)
	velocity.sort(key=lambda row: row["rate"], reverse=True)
	velocity = velocity[:INVENTORY_VELOCITY_LIMIT]

	# Dead stock: on the shelf with nothing sold in the last 30 days - the section's own subtitle
	# says exactly that, so that is the window this list is scoped to.
	dead_stock = []
	for row in rows:
		if flt(row["stock"]) <= 0:
			continue
		item_code = row["item_code"]
		if sales_30d.get(item_code, {}).get("units", 0):
			continue
		last_sold = sales_lifetime.get(item_code, {}).get("last_sold")
		dead_stock.append(
			{
				"product": row["product"],
				"variant": row["option"],
				"sku": item_code,
				"stock": row["stock"],
				"last_sold_days": date_diff(today, last_sold) if last_sold else None,
				"value": flt(row["stock"]) * rates.get(item_code, 0),
			}
		)
	dead_stock.sort(key=lambda row: row["value"], reverse=True)
	dead_stock = dead_stock[:DEAD_STOCK_LIMIT]
	dead_stock_value = sum(row["value"] for row in dead_stock)

	# Stock value over time: the warehouse's day-by-day on-hand qty from analytics_dashboard's ledger
	# walk-back, priced at today's blended average - this data model carries no historical valuation.
	movement = get_stock_movement(str(start), str(today))
	value_by_month = {}
	for label, on_hand in zip(movement["labels"], movement["on_hand"], strict=True):
		# Walking the ledger back through this shop's single seeded Stock Reconciliation can drift below
		# zero for the months before it - clamp rather than show a shelf holding negative units.
		value_by_month[month_key(label)] = max(flt(on_hand), 0.0) * avg_price
	stock_value_by_month = [
		{"month": key, "label": formatdate(f"{key}-01", "MMM"), "value": round(value_by_month.get(key, 0), 2)}
		for key in sorted(build_month_buckets(start, today))
	]

	return {
		"currency": get_store_currency(),
		"stats": {
			"stock_value": {"value": round(stock_value_now, 2)},
			"units_on_hand": {"value": units_on_hand_now},
			"days_of_cover": {
				"value": round(units_on_hand_now / (units_sold_30d / 30), 1) if units_sold_30d else None
			},
			"dead_stock_value": {"value": round(dead_stock_value, 2)},
		},
		"stock_value_by_month": stock_value_by_month,
		"velocity": velocity,
		"dead_stock": dead_stock,
	}


def get_sessions_by_month(start, today):
	"""Distinct sessions per month, bucketed in SQL - one GROUP BY over 34k+ events, never a Python loop.
	DATE_FORMAT token syntax differs between MariaDB and Postgres, so the format is picked per backend."""
	analytics_event = frappe.qb.DocType("Storefront Analytics Event")
	date_format = "%Y-%m" if frappe.db.db_type != "postgres" else "YYYY-MM"
	month_bucket = DateFormat(analytics_event.creation, date_format)
	rows = (
		frappe.qb.from_(analytics_event)
		.select(month_bucket.as_("month"), Count(analytics_event.session_id).distinct())
		.where(analytics_event.creation >= start)
		.where(analytics_event.creation < add_days(today, 1))
		.groupby(month_bucket)
		.run()
	)
	sessions_by_key = {row[0]: cint(row[1]) for row in rows}
	return [
		{"month": key, "label": formatdate(f"{key}-01", "MMM"), "sessions": sessions_by_key.get(key, 0)}
		for key in sorted(build_month_buckets(start, today))
	]


def get_channel_split(from_date, to_date):
	"""Session count by first-touch channel only - a donut needs a handful of slices, not
	analytics_dashboard.get_traffic_sources' full source x medium x campaign grouping."""
	analytics_event = frappe.qb.DocType("Storefront Analytics Event")
	start, end = get_window(from_date, to_date)
	source = Coalesce(NullIf(analytics_event.utm_source, ""), "Direct")
	sessions = Count(analytics_event.session_id).distinct()
	rows = (
		frappe.qb.from_(analytics_event)
		.select(source, sessions)
		.where(in_window(analytics_event.creation, start, end))
		.groupby(source)
		.orderby(sessions, order=Order.desc)
		.run()
	)
	return [{"source": row[0], "sessions": cint(row[1])} for row in rows]


@frappe.whitelist()
def get_storefront_report(months: int = REPORT_MONTHS_DEFAULT):
	"""Sessions/funnel/traffic for the trailing N months - a thin wrapper over analytics_dashboard.py's
	already SQL-aggregated storefront queries, so it cannot disagree with the Desk analytics dashboard."""
	frappe.only_for("System Manager")

	start, today, months = month_window(months)
	from_date, to_date = str(start), str(today)

	current = get_period_kpis(from_date, to_date)
	# get_previous_window returns date objects, not strings - get_funnel below is a whitelisted,
	# type-hinted function, and frappe enforces its `str` params even on a direct in-process call.
	previous_from, previous_to = (str(value) for value in get_previous_window(from_date, to_date))
	previous = get_period_kpis(previous_from, previous_to)

	funnel = get_funnel(from_date, to_date)["stages"]
	previous_funnel = get_funnel(previous_from, previous_to)["stages"]

	def stage_count(stages, key):
		return next((row["count"] for row in stages if row["key"] == key), 0)

	add_to_cart_rate = get_rate(stage_count(funnel, "added_to_cart"), stage_count(funnel, "sessions"))
	checkout_completion_rate = get_rate(
		stage_count(funnel, "purchased"), stage_count(funnel, "reached_checkout")
	)
	previous_add_to_cart_rate = get_rate(
		stage_count(previous_funnel, "added_to_cart"), stage_count(previous_funnel, "sessions")
	)
	previous_checkout_completion_rate = get_rate(
		stage_count(previous_funnel, "purchased"), stage_count(previous_funnel, "reached_checkout")
	)

	return {
		"stats": {
			"sessions": {"value": current["sessions"], "previous": previous["sessions"]},
			"conversion_rate": {"value": current["conversion_rate"], "previous": previous["conversion_rate"]},
			"add_to_cart_rate": {"value": add_to_cart_rate, "previous": previous_add_to_cart_rate},
			"checkout_completion_rate": {
				"value": checkout_completion_rate,
				"previous": previous_checkout_completion_rate,
			},
		},
		"sessions_by_month": get_sessions_by_month(start, today),
		"channels": [
			{"channel": row["source"], "sessions": row["sessions"]}
			for row in get_channel_split(from_date, to_date)
		],
		"funnel": [{"stage": row["label"], "count": row["count"]} for row in funnel],
		"top_pages": [
			{"page": row["path"], "views": row["sessions"], "conversion": row["conversion_rate"]}
			for row in get_landing_pages(from_date, to_date, limit=TOP_PAGES_LIMIT)
		],
		# Storefront Analytics Event carries no search-term field (event/session/device/item_code/path/utm_*
		# only), so there is nothing real to report. See docs/commera-open-questions.md.
		"search_terms": [],
	}
