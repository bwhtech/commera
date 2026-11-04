"""Read-side aggregates for the storefront analytics Desk dashboard (System Manager only)."""

import frappe
from frappe.query_builder import Case, Order
from frappe.query_builder.functions import Coalesce, Count, Max, Min, NullIf, Sum
from frappe.utils.data import (
	add_days,
	add_to_date,
	cint,
	date_diff,
	flt,
	get_datetime,
	getdate,
	now_datetime,
)

from commera.analytics import facebook, ga4
from commera.api.admin.inventory import get_ecommerce_warehouse
from commera.api.admin.orders import is_webshop_order
from commera.utils import get_store_currency

KNOWN_PROVIDER_ERRORS = {
	"meta": "Meta denied pixel stats — the token needs ads_read AND the pixel's connected ad account assigned to the system user",
	"ga4": "Service account has no access to the GA4 property — grant Viewer to the service-account email",
}
FUNNEL_STAGES = (
	("viewed_product", "Viewed Product", "view_item"),
	("added_to_cart", "Added to Cart", "add_to_cart"),
	("reached_checkout", "Reached Checkout", "begin_checkout"),
	("purchased", "Purchased", "purchase"),
)
ABANDONED_CARTS_LIMIT = 20
# source x medium x campaign is a guest-controlled grouping, so the cap bounds the distinct groups
TRAFFIC_SOURCES_LIMIT = 50
# engagement sorts by conversion rate, so rank a wider by-views pool first, then slice
ENGAGEMENT_CANDIDATE_LIMIT = 100
ITEM_SOURCES_LIMIT = 10
RECENT_ORDERS_LIMIT = 5


def get_window(from_date, to_date):
	# to_date is inclusive: creation < to_date + 1 day
	return getdate(from_date), add_days(getdate(to_date), 1)


def get_previous_window(from_date, to_date):
	period_days = date_diff(to_date, from_date) + 1
	previous_to = add_days(getdate(from_date), -1)
	return add_days(previous_to, 1 - period_days), previous_to


def get_rate(numerator, denominator):
	return round(numerator / denominator * 100, 1) if denominator else 0.0


def get_days(start, end):
	days = []
	day = start
	while day < end:
		days.append(str(day))
		day = add_days(day, 1)
	return days


def in_window(field, start, end):
	return (field >= start) & (field < end)


def distinct_sessions(analytics_event):
	return Count(analytics_event.session_id).distinct()


def distinct_purchase_sessions(analytics_event):
	return Count(Case().when(analytics_event.event == "purchase", analytics_event.session_id)).distinct()


def get_item_details(item_codes):
	if not item_codes:
		return {}
	rows = frappe.get_all("Item", filters={"name": ("in", item_codes)}, fields=["name", "item_name"])
	return {row.name: row for row in rows}


def get_period_kpis(from_date, to_date):
	start, end = get_window(from_date, to_date)
	sales_order = frappe.qb.DocType("Sales Order")
	previous_buyers = (
		frappe.qb.from_(sales_order)
		.select(sales_order.customer)
		.where(is_webshop_order(sales_order))
		.where(sales_order.transaction_date < start)
	)
	order_row = (
		frappe.qb.from_(sales_order)
		.select(
			Sum(sales_order.base_grand_total),
			Count(sales_order.name),
			Count(sales_order.customer).distinct(),
			Count(Case().when(sales_order.customer.isin(previous_buyers), sales_order.customer)).distinct(),
		)
		.where(is_webshop_order(sales_order))
		.where(in_window(sales_order.transaction_date, start, end))
		.run()
	)[0]
	analytics_event = frappe.qb.DocType("Storefront Analytics Event")
	event_row = (
		frappe.qb.from_(analytics_event)
		.select(distinct_sessions(analytics_event), distinct_purchase_sessions(analytics_event))
		.where(in_window(analytics_event.creation, start, end))
		.run()
	)[0]
	total_sales, orders = flt(order_row[0]), cint(order_row[1])
	customers, returning_customers = cint(order_row[2]), cint(order_row[3])
	sessions, purchase_sessions = cint(event_row[0]), cint(event_row[1])
	return {
		"total_sales": total_sales,
		"orders": orders,
		"sessions": sessions,
		"conversion_rate": get_rate(purchase_sessions, sessions),
		"aov": round(total_sales / orders, 2) if orders else 0.0,
		"returning_customer_rate": get_rate(returning_customers, customers),
	}


def is_provider_configured(provider, settings):
	if provider == "ga4":
		return bool(
			settings.enable_ga4
			and settings.ga4_measurement_id
			and settings.ga4_property_id
			and settings.get_password("ga4_service_account_json", raise_exception=False)
		)
	return bool(
		settings.enable_facebook
		and settings.fb_pixel_id
		and settings.get_password("fb_access_token", raise_exception=False)
	)


def get_provider_summary(provider):
	"""(summary, error) — the external read-backs raise on bad credentials; degrade instead of 500ing."""
	fetch_summary = ga4.get_summary if provider == "ga4" else facebook.get_summary
	try:
		return fetch_summary(), None
	except Exception as exception:
		status_code = getattr(getattr(exception, "response", None), "status_code", None)
		message = str(exception)
		if status_code in (400, 403) or "400" in message or "403" in message:
			return None, KNOWN_PROVIDER_ERRORS[provider]
		return None, message[:140] or exception.__class__.__name__


def get_provider_health(provider, configured):
	# unconfigured short-circuits: calling get_summary would report a misleading zero-total ok
	if not configured:
		return {"configured": False, "ok": False, "purchases_30d": None, "error": None}
	summary, error = get_provider_summary(provider)
	if error:
		return {"configured": True, "ok": False, "purchases_30d": None, "error": error}
	purchase_key = "purchase" if provider == "ga4" else "Purchase"
	return {
		"configured": True,
		"ok": True,
		"purchases_30d": cint(summary["totals"][purchase_key]),
		"error": None,
	}


@frappe.whitelist()
def get_overview(from_date: str, to_date: str):
	frappe.only_for("System Manager")
	current = get_period_kpis(from_date, to_date)
	previous_from, previous_to = get_previous_window(from_date, to_date)
	previous = get_period_kpis(previous_from, previous_to)
	return {
		# base_grand_total is company currency; Global Defaults is a separate setting and mislabels the tiles.
		"currency": get_store_currency(),
		"kpis": {key: {"value": current[key], "previous": previous[key]} for key in current},
	}


@frappe.whitelist()
def get_sales_timeseries(from_date: str, to_date: str):
	frappe.only_for("System Manager")
	start, end = get_window(from_date, to_date)
	sales_order = frappe.qb.DocType("Sales Order")
	rows = (
		frappe.qb.from_(sales_order)
		.select(sales_order.transaction_date, Sum(sales_order.base_grand_total), Count(sales_order.name))
		.where(is_webshop_order(sales_order))
		.where(in_window(sales_order.transaction_date, start, end))
		.groupby(sales_order.transaction_date)
		.run()
	)
	rows_by_day = {str(row[0]): row for row in rows}
	labels, sales, orders = [], [], []
	day = start
	while day < end:
		row = rows_by_day.get(str(day))
		labels.append(str(day))
		sales.append(flt(row[1]) if row else 0.0)
		orders.append(cint(row[2]) if row else 0)
		day = add_days(day, 1)
	return {"labels": labels, "sales": sales, "orders": orders}


@frappe.whitelist()
def get_funnel(from_date: str, to_date: str, device: str | None = None):
	frappe.only_for("System Manager")
	# clients send lowercase device keys; the Select field stores title case
	device = device.title() if device else None
	start, end = get_window(from_date, to_date)
	analytics_event = frappe.qb.DocType("Storefront Analytics Event")
	total_query = (
		frappe.qb.from_(analytics_event)
		.select(distinct_sessions(analytics_event))
		.where(in_window(analytics_event.creation, start, end))
	)
	stage_query = (
		frappe.qb.from_(analytics_event)
		.select(analytics_event.event, distinct_sessions(analytics_event))
		.where(in_window(analytics_event.creation, start, end))
		.groupby(analytics_event.event)
	)
	if device:
		total_query = total_query.where(analytics_event.device == device)
		stage_query = stage_query.where(analytics_event.device == device)
	stage_counts = {row[0]: cint(row[1]) for row in stage_query.run()}
	stages = [{"key": "sessions", "label": "Sessions", "count": cint(total_query.run()[0][0])}]
	for key, label, event in FUNNEL_STAGES:
		stages.append({"key": key, "label": label, "count": stage_counts.get(event, 0)})
	return {"stages": stages}


@frappe.whitelist()
def get_live_view():
	frappe.only_for("System Manager")
	now = now_datetime()
	analytics_event = frappe.qb.DocType("Storefront Analytics Event")
	visitors_now = (
		frappe.qb.from_(analytics_event)
		.select(distinct_sessions(analytics_event))
		.where(analytics_event.creation >= add_to_date(now, minutes=-5))
		.run()
	)[0][0]
	recent_rows = (
		frappe.qb.from_(analytics_event)
		.select(analytics_event.event, analytics_event.session_id)
		.where(analytics_event.creation >= add_to_date(now, minutes=-10))
		.where(analytics_event.event.isin(["add_to_cart", "begin_checkout", "purchase"]))
		.run()
	)
	recent_sessions = {"add_to_cart": set(), "begin_checkout": set(), "purchase": set()}
	for event, session_id in recent_rows:
		if session_id:
			recent_sessions[event].add(session_id)
	today = getdate(now)
	today_sessions = (
		frappe.qb.from_(analytics_event)
		.select(distinct_sessions(analytics_event))
		.where(analytics_event.creation >= today)
		.run()
	)[0][0]
	sales_order = frappe.qb.DocType("Sales Order")
	sales_row = (
		frappe.qb.from_(sales_order)
		.select(Count(sales_order.name), Sum(sales_order.base_grand_total))
		.where(is_webshop_order(sales_order))
		.where(sales_order.transaction_date == today)
		.run()
	)[0]
	return {
		"visitors_now": cint(visitors_now),
		"today": {"sessions": cint(today_sessions), "orders": cint(sales_row[0]), "sales": flt(sales_row[1])},
		"active_carts": len(recent_sessions["add_to_cart"] - recent_sessions["purchase"]),
		"checking_out": len(recent_sessions["begin_checkout"] - recent_sessions["purchase"]),
	}


@frappe.whitelist()
def get_top_products(from_date: str, to_date: str, sort_by: str = "revenue", limit: int = 10):
	frappe.only_for("System Manager")
	if sort_by not in ("revenue", "units"):
		frappe.throw(frappe._("sort_by must be revenue or units"))
	start, end = get_window(from_date, to_date)
	sales_order = frappe.qb.DocType("Sales Order")
	order_item = frappe.qb.DocType("Sales Order Item")
	units, revenue = Sum(order_item.qty), Sum(order_item.base_amount)
	rows = (
		frappe.qb.from_(order_item)
		.join(sales_order)
		.on(order_item.parent == sales_order.name)
		.select(order_item.item_code, units, revenue)
		.where(is_webshop_order(sales_order))
		.where(in_window(sales_order.transaction_date, start, end))
		.groupby(order_item.item_code)
		.orderby(units if sort_by == "units" else revenue, order=Order.desc)
		.limit(cint(limit) or 10)
		.run()
	)
	details = get_item_details([row[0] for row in rows])
	return [
		{
			"item_code": row[0],
			"item_name": details.get(row[0], {}).get("item_name") or row[0],
			"units": cint(row[1]),
			"revenue": flt(row[2]),
		}
		for row in rows
	]


@frappe.whitelist()
def get_product_engagement(from_date: str, to_date: str, limit: int = 15):
	frappe.only_for("System Manager")
	start, end = get_window(from_date, to_date)
	analytics_event = frappe.qb.DocType("Storefront Analytics Event")
	views = Count(Case().when(analytics_event.event == "view_item", analytics_event.name))
	adds = Count(Case().when(analytics_event.event == "add_to_cart", analytics_event.name))
	rows = (
		frappe.qb.from_(analytics_event)
		.select(analytics_event.item_code, views, adds)
		.where(in_window(analytics_event.creation, start, end))
		.where(analytics_event.event.isin(["view_item", "add_to_cart"]))
		.where(analytics_event.item_code.isnotnull())
		.groupby(analytics_event.item_code)
		.orderby(views, order=Order.desc)
		.limit(ENGAGEMENT_CANDIDATE_LIMIT)
		.run()
	)
	item_codes = [row[0] for row in rows]
	purchased_units = {}
	if item_codes:
		# scanning items_json of every purchase session is too expensive; SO Item units are equivalent
		sales_order = frappe.qb.DocType("Sales Order")
		order_item = frappe.qb.DocType("Sales Order Item")
		purchased_rows = (
			frappe.qb.from_(order_item)
			.join(sales_order)
			.on(order_item.parent == sales_order.name)
			.select(order_item.item_code, Sum(order_item.qty))
			.where(is_webshop_order(sales_order))
			.where(in_window(sales_order.transaction_date, start, end))
			.where(order_item.item_code.isin(item_codes))
			.groupby(order_item.item_code)
			.run()
		)
		purchased_units = {row[0]: cint(row[1]) for row in purchased_rows}
	details = get_item_details(item_codes)
	engagement = []
	for item_code, view_count, add_count in rows:
		view_count, add_count = cint(view_count), cint(add_count)
		purchases = purchased_units.get(item_code, 0)
		engagement.append(
			{
				"item_code": item_code,
				"item_name": details.get(item_code, {}).get("item_name") or item_code,
				"views": view_count,
				"adds": add_count,
				"purchases": purchases,
				"cart_to_view_rate": get_rate(add_count, view_count),
				"purchase_to_view_rate": get_rate(purchases, view_count),
			}
		)
	engagement.sort(key=lambda row: (row["purchase_to_view_rate"], row["views"]), reverse=True)
	return engagement[: cint(limit) or 15]


@frappe.whitelist()
def get_traffic_sources(from_date: str, to_date: str):
	frappe.only_for("System Manager")
	start, end = get_window(from_date, to_date)
	analytics_event = frappe.qb.DocType("Storefront Analytics Event")
	source = Coalesce(NullIf(analytics_event.utm_source, ""), "Direct")
	medium = Coalesce(analytics_event.utm_medium, "")
	# direct and organic traffic has no campaign; left empty rather than given a placeholder
	campaign = Coalesce(analytics_event.utm_campaign, "")
	sessions = distinct_sessions(analytics_event)
	rows = (
		frappe.qb.from_(analytics_event)
		.select(
			source,
			medium,
			campaign,
			sessions,
			distinct_purchase_sessions(analytics_event),
			Sum(Case().when(analytics_event.event == "purchase", analytics_event.value)),
		)
		.where(in_window(analytics_event.creation, start, end))
		.groupby(source, medium, campaign)
		.orderby(sessions, order=Order.desc)
		# guests control utm_* values, so distinct groups are unbounded without a cap
		.limit(TRAFFIC_SOURCES_LIMIT)
		.run()
	)
	return [
		{
			"source": row[0],
			"medium": row[1] or "",
			"campaign": row[2] or "",
			"sessions": cint(row[3]),
			"orders": cint(row[4]),
			"revenue": flt(row[5]),
			"conversion_rate": get_rate(cint(row[4]), cint(row[3])),
		}
		for row in rows
	]


@frappe.whitelist()
def get_device_split(from_date: str, to_date: str):
	frappe.only_for("System Manager")
	start, end = get_window(from_date, to_date)
	analytics_event = frappe.qb.DocType("Storefront Analytics Event")
	device = Coalesce(NullIf(analytics_event.device, ""), "Unknown")
	sessions = distinct_sessions(analytics_event)
	rows = (
		frappe.qb.from_(analytics_event)
		.select(device, sessions, distinct_purchase_sessions(analytics_event))
		.where(in_window(analytics_event.creation, start, end))
		.groupby(device)
		.orderby(sessions, order=Order.desc)
		.run()
	)
	return [
		{"device": row[0], "sessions": cint(row[1]), "conversion_rate": get_rate(cint(row[2]), cint(row[1]))}
		for row in rows
	]


@frappe.whitelist()
def get_landing_pages(from_date: str, to_date: str, limit: int = 8):
	frappe.only_for("System Manager")
	start, end = get_window(from_date, to_date)
	analytics_event = frappe.qb.DocType("Storefront Analytics Event")
	first_touch = (
		frappe.qb.from_(analytics_event)
		.select(
			analytics_event.session_id.as_("session_id"),
			Min(analytics_event.creation).as_("first_creation"),
		)
		.where(analytics_event.event == "page_view")
		.where(in_window(analytics_event.creation, start, end))
		.where(analytics_event.session_id.isnotnull())
		.groupby(analytics_event.session_id)
	)
	purchases = (
		frappe.qb.from_(analytics_event)
		.select(analytics_event.session_id.as_("session_id"))
		.distinct()
		.where(analytics_event.event == "purchase")
		.where(in_window(analytics_event.creation, start, end))
	)
	landing_event = frappe.qb.DocType("Storefront Analytics Event").as_("landing_event")
	path = Coalesce(landing_event.path, "/")
	sessions = Count(first_touch.session_id).distinct()
	rows = (
		frappe.qb.from_(first_touch)
		.join(landing_event)
		.on(
			(landing_event.session_id == first_touch.session_id)
			& (landing_event.creation == first_touch.first_creation)
		)
		.left_join(purchases)
		.on(purchases.session_id == first_touch.session_id)
		.select(path, sessions, Count(purchases.session_id).distinct())
		.where(landing_event.event == "page_view")
		.groupby(path)
		.orderby(sessions, order=Order.desc)
		.limit(cint(limit) or 8)
		.run()
	)
	return [
		{"path": row[0], "sessions": cint(row[1]), "conversion_rate": get_rate(cint(row[2]), cint(row[1]))}
		for row in rows
	]


@frappe.whitelist()
def get_abandoned_carts(from_date: str, to_date: str):
	frappe.only_for("System Manager")
	start, end = get_window(from_date, to_date)
	analytics_event = frappe.qb.DocType("Storefront Analytics Event")
	adds = Count(Case().when(analytics_event.event == "add_to_cart", analytics_event.name))
	session_rows = (
		frappe.qb.from_(analytics_event)
		.select(
			analytics_event.session_id,
			adds,
			Sum(Case().when(analytics_event.event == "add_to_cart", analytics_event.value)),
			Max(analytics_event.creation),
			Count(Case().when(analytics_event.event == "purchase", analytics_event.name)),
			Max(analytics_event.visitor_user),
		)
		.where(in_window(analytics_event.creation, start, end))
		.where(analytics_event.session_id.isnotnull())
		.groupby(analytics_event.session_id)
		.having(adds > 0)
		.run()
	)
	stale_before = add_to_date(now_datetime(), hours=-1)
	abandoned, recovered = [], []
	for session_id, add_count, cart_value, last_activity, purchase_count, visitor_user in session_rows:
		cart = {
			"session_id": session_id,
			"items_count": cint(add_count),
			"value": flt(cart_value),
			"last_activity": get_datetime(last_activity),
			"visitor_user": visitor_user,
			"status": "Recovered" if cint(purchase_count) else "Abandoned",
		}
		if cart["status"] == "Recovered":
			recovered.append(cart)
		elif cart["last_activity"] <= stale_before:
			abandoned.append(cart)
	listed = sorted(abandoned + recovered, key=lambda cart: cart["last_activity"], reverse=True)
	listed = listed[:ABANDONED_CARTS_LIMIT]
	quotations_by_session = {}
	if listed:
		quotation_rows = frappe.get_all(
			"Quotation",
			filters={
				"custom_analytics_session_id": ("in", [cart["session_id"] for cart in listed]),
				"docstatus": 0,
				"order_type": "Shopping Cart",
			},
			fields=["name", "custom_analytics_session_id", "contact_email", "party_name"],
			order_by="modified desc",
		)
		for quotation in quotation_rows:
			quotations_by_session.setdefault(quotation.custom_analytics_session_id, quotation)
	carts = []
	for cart in listed:
		quotation = quotations_by_session.get(cart["session_id"])
		status = cart["status"]
		if status == "Abandoned" and (cart["visitor_user"] or (quotation and quotation.contact_email)):
			status = "Recoverable"
		carts.append(
			{
				"session_id": cart["session_id"],
				"customer": (quotation and quotation.party_name) or cart["visitor_user"],
				"email": (quotation and quotation.contact_email) or cart["visitor_user"],
				"items_count": cart["items_count"],
				"value": cart["value"],
				"last_activity": cart["last_activity"].isoformat(),
				"status": status,
				"quotation": quotation.name if quotation else None,
			}
		)
	return {
		"stats": {
			"count": len(abandoned),
			"value": flt(sum(cart["value"] for cart in abandoned)),
			"rate": get_rate(len(abandoned), len(abandoned) + len(recovered)),
		},
		"carts": carts,
	}


@frappe.whitelist()
def get_sales_heatmap(from_date: str, to_date: str):
	frappe.only_for("System Manager")
	start, end = get_window(from_date, to_date)
	sales_order = frappe.qb.DocType("Sales Order")
	rows = (
		frappe.qb.from_(sales_order)
		.select(sales_order.creation)
		.where(is_webshop_order(sales_order))
		.where(in_window(sales_order.creation, start, end))
		.run()
	)
	matrix = [[0] * 24 for _ in range(7)]
	for (creation,) in rows:
		timestamp = get_datetime(creation)
		matrix[timestamp.weekday()][timestamp.hour] += 1
	return {"matrix": matrix, "max": max(cell for row in matrix for cell in row)}


@frappe.whitelist()
def get_tracking_health():
	frappe.only_for("System Manager")
	now = now_datetime()
	analytics_event = frappe.qb.DocType("Storefront Analytics Event")
	first_party_row = (
		frappe.qb.from_(analytics_event)
		.select(
			Count(Case().when(analytics_event.creation >= add_to_date(now, hours=-24), analytics_event.name)),
			Count(Case().when(analytics_event.event == "purchase", analytics_event.name)),
		)
		.where(analytics_event.creation >= add_days(now, -30))
		.run()
	)[0]
	settings = frappe.get_cached_doc("Analytics Settings")
	return {
		"first_party": {"events_24h": cint(first_party_row[0]), "purchases_30d": cint(first_party_row[1])},
		"ga4": get_provider_health("ga4", is_provider_configured("ga4", settings)),
		"meta": get_provider_health("meta", is_provider_configured("meta", settings)),
	}


@frappe.whitelist()
def get_external_summaries():
	frappe.only_for("System Manager")
	settings = frappe.get_cached_doc("Analytics Settings")
	summaries = {}
	for provider in ("ga4", "meta"):
		if not is_provider_configured(provider, settings):
			summaries[provider] = {"configured": False, "summary": None, "error": None}
			continue
		summary, error = get_provider_summary(provider)
		summaries[provider] = {"configured": True, "summary": summary, "error": error}
	return summaries


@frappe.whitelist()
def get_item_analytics(item_code: str, from_date: str, to_date: str):
	frappe.only_for("System Manager")
	item_name = frappe.db.get_value("Item", item_code, "item_name")
	if not item_name:
		frappe.throw(frappe._("Item {0} does not exist").format(item_code))
	start, end = get_window(from_date, to_date)
	analytics_event = frappe.qb.DocType("Storefront Analytics Event")
	# Python day-bucketing because Postgres has no DATE() function for a qb groupby
	event_rows = (
		frappe.qb.from_(analytics_event)
		.select(
			analytics_event.event,
			analytics_event.creation,
			analytics_event.device,
			analytics_event.utm_source,
			analytics_event.utm_medium,
		)
		.where(in_window(analytics_event.creation, start, end))
		.where(analytics_event.item_code == item_code)
		.where(analytics_event.event.isin(["view_item", "add_to_cart"]))
		.run()
	)
	views = adds = 0
	views_by_day, adds_by_day, views_by_device, source_stats = {}, {}, {}, {}
	for event, creation, device, utm_source, utm_medium in event_rows:
		day = str(get_datetime(creation).date())
		stats = source_stats.setdefault((utm_source or "Direct", utm_medium or ""), {"views": 0, "adds": 0})
		if event == "view_item":
			views += 1
			views_by_day[day] = views_by_day.get(day, 0) + 1
			views_by_device[device or "Unknown"] = views_by_device.get(device or "Unknown", 0) + 1
			stats["views"] += 1
		else:
			adds += 1
			adds_by_day[day] = adds_by_day.get(day, 0) + 1
			stats["adds"] += 1
	checkouts = (
		frappe.qb.from_(analytics_event)
		.select(Count(analytics_event.name))
		.where(in_window(analytics_event.creation, start, end))
		.where(analytics_event.event == "begin_checkout")
		# accepted approximation: begin_checkout snapshots carry the code inside items_json
		.where(analytics_event.items_json.like(f"%{item_code}%"))
		.run()
	)[0][0]
	sales_order = frappe.qb.DocType("Sales Order")
	order_item = frappe.qb.DocType("Sales Order Item")
	order_rows = (
		frappe.qb.from_(order_item)
		.join(sales_order)
		.on(order_item.parent == sales_order.name)
		.select(
			order_item.parent,
			sales_order.transaction_date,
			Sum(order_item.qty),
			Sum(order_item.base_amount),
		)
		.where(is_webshop_order(sales_order))
		.where(in_window(sales_order.transaction_date, start, end))
		.where(order_item.item_code == item_code)
		.groupby(order_item.parent, sales_order.transaction_date)
		.run()
	)
	units_sold = cint(sum(cint(row[2]) for row in order_rows))
	revenue = flt(sum(flt(row[3]) for row in order_rows))
	units_by_day = {}
	for row in order_rows:
		day = str(row[1])
		units_by_day[day] = units_by_day.get(day, 0) + cint(row[2])
	recent_orders = sorted(order_rows, key=lambda row: row[1], reverse=True)[:RECENT_ORDERS_LIMIT]
	store_units = (
		frappe.qb.from_(order_item)
		.join(sales_order)
		.on(order_item.parent == sales_order.name)
		.select(Sum(order_item.qty))
		.where(is_webshop_order(sales_order))
		.where(in_window(sales_order.transaction_date, start, end))
		.run()
	)[0][0]
	store_views = (
		frappe.qb.from_(analytics_event)
		.select(Count(analytics_event.name))
		.where(in_window(analytics_event.creation, start, end))
		.where(analytics_event.event == "view_item")
		.run()
	)[0][0]
	days = get_days(start, end)
	top_sources = sorted(source_stats.items(), key=lambda entry: entry[1]["views"], reverse=True)
	return {
		"item_code": item_code,
		"item_name": item_name,
		"totals": {
			"views": views,
			"adds": adds,
			"checkouts": cint(checkouts),
			"units_sold": units_sold,
			"revenue": revenue,
			"cart_to_view_rate": get_rate(adds, views),
			"purchase_to_view_rate": get_rate(units_sold, views),
			"store_avg_purchase_to_view_rate": get_rate(cint(store_units), cint(store_views)),
		},
		"daily": {
			"labels": days,
			"views": [views_by_day.get(day, 0) for day in days],
			"adds": [adds_by_day.get(day, 0) for day in days],
			"units": [units_by_day.get(day, 0) for day in days],
		},
		"devices": [
			{"device": device, "views": view_count}
			for device, view_count in sorted(
				views_by_device.items(), key=lambda entry: entry[1], reverse=True
			)
		],
		"sources": [
			{"source": source, "medium": medium, "views": stats["views"], "adds": stats["adds"]}
			for (source, medium), stats in top_sources[:ITEM_SOURCES_LIMIT]
		],
		"recent_orders": [
			{"order": row[0], "date": str(row[1]), "qty": cint(row[2]), "amount": flt(row[3])}
			for row in recent_orders
		],
	}


@frappe.whitelist()
def get_stock_movement(from_date: str, to_date: str):
	"""How stock moved through the shop warehouse each day, and the level it left behind."""
	frappe.only_for("System Manager")
	warehouse = get_ecommerce_warehouse()
	start, end = get_window(from_date, to_date)
	days = get_days(start, end)
	if not warehouse:
		return {"warehouse": None, "labels": days, "units_in": [], "units_out": [], "on_hand": []}

	stock_ledger = frappe.qb.DocType("Stock Ledger Entry")
	incoming = Sum(Case().when(stock_ledger.actual_qty > 0, stock_ledger.actual_qty).else_(0))
	outgoing = Sum(Case().when(stock_ledger.actual_qty < 0, -stock_ledger.actual_qty).else_(0))
	movement = (
		frappe.qb.from_(stock_ledger)
		.select(stock_ledger.posting_date, incoming.as_("units_in"), outgoing.as_("units_out"))
		.where(stock_ledger.warehouse == warehouse)
		.where(stock_ledger.is_cancelled == 0)
		.where(stock_ledger.posting_date >= start)
		.where(stock_ledger.posting_date < end)
		.groupby(stock_ledger.posting_date)
	).run(as_dict=True)

	by_day = {str(row.posting_date): row for row in movement}
	units_in = [flt(by_day[day].units_in) if day in by_day else 0.0 for day in days]
	units_out = [flt(by_day[day].units_out) if day in by_day else 0.0 for day in days]

	# Bin only knows today, so the level on each past day is walked back from it through the ledger.
	bin_table = frappe.qb.DocType("Bin")
	on_hand_now = (
		frappe.qb.from_(bin_table).select(Sum(bin_table.actual_qty)).where(bin_table.warehouse == warehouse)
	).run()
	closing = flt(on_hand_now[0][0]) if on_hand_now else 0.0

	since_window = (
		frappe.qb.from_(stock_ledger)
		.select(Sum(stock_ledger.actual_qty))
		.where(stock_ledger.warehouse == warehouse)
		.where(stock_ledger.is_cancelled == 0)
		.where(stock_ledger.posting_date >= end)
	).run()
	closing -= flt(since_window[0][0]) if since_window else 0.0

	on_hand = []
	for index in reversed(range(len(days))):
		on_hand.insert(0, closing)
		closing -= units_in[index] - units_out[index]

	return {
		"warehouse": warehouse,
		"labels": days,
		"units_in": units_in,
		"units_out": units_out,
		"on_hand": on_hand,
	}
