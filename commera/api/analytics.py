import frappe
from frappe.utils.data import cint, cstr, flt

from commera.analytics import events, facebook, ga4
from commera.utils import rate_limit_per_method

CLIENT_EVENTS = ("page_view", "view_item", "add_to_cart", "begin_checkout")


def get_capture_payload():
	payload = frappe.request.get_json(silent=True) if frappe.request else None
	if not isinstance(payload, dict):
		payload = frappe.form_dict
	return payload


# nosemgrep: frappe-semgrep-rules.rules.security.guest-whitelisted-method  # anonymous beacon: validated, clamped, rate-limited
@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit_per_method(limit=600, seconds=60)
def capture():
	if not events.is_first_party_enabled():
		return
	payload = get_capture_payload()
	# purchase is deliberately excluded — the server logs it at order submit
	if payload.get("event") not in CLIENT_EVENTS:
		frappe.throw(frappe._("Unknown analytics event"))

	item_code = cstr(payload.get("item_code") or "")
	if item_code and not frappe.db.exists("Item", item_code):
		item_code = None

	# ponytail: one INSERT per beacon, revisit with a batched buffer if the events table
	# outgrows the write budget (roughly: sustained page views above a few hundred/sec)
	frappe.get_doc(
		{
			"doctype": "Storefront Analytics Event",
			"event": payload.get("event"),
			"session_id": events.clip(payload.get("session_id"), 64),
			"visitor_user": events.get_visitor_user(),
			"device": events.get_device(events.get_user_agent()),
			"item_code": item_code or None,
			"qty": cint(payload.get("qty")),
			"value": flt(payload.get("value")),
			"currency": events.clip(payload.get("currency"), 8),
			"path": events.clip(payload.get("path"), 255),
			"referrer": events.clip(payload.get("referrer"), 255),
			"utm_source": events.clip(payload.get("utm_source"), 140),
			"utm_medium": events.clip(payload.get("utm_medium"), 140),
			"utm_campaign": events.clip(payload.get("utm_campaign"), 140),
			"utm_term": events.clip(payload.get("utm_term"), 140),
			"utm_content": events.clip(payload.get("utm_content"), 140),
			"items_json": events.get_items_snapshot(payload.get("items")),
		}
	).insert(ignore_permissions=True)


@frappe.whitelist()
def get_facebook_summary():
	frappe.only_for("System Manager")
	return facebook.get_summary()


def event_card(event):
	frappe.only_for("System Manager")
	# broken credentials must degrade to 0, not error-spam the Desk dashboard
	try:
		totals = facebook.get_summary()["totals"]
	except Exception:
		totals = {}
	return {"value": cint(totals.get(event)), "fieldtype": "Int"}


@frappe.whitelist()
def pageview_count(filters: dict | list | str | None = None):
	return event_card("PageView")


@frappe.whitelist()
def viewcontent_count(filters: dict | list | str | None = None):
	return event_card("ViewContent")


@frappe.whitelist()
def addtocart_count(filters: dict | list | str | None = None):
	return event_card("AddToCart")


@frappe.whitelist()
def initiatecheckout_count(filters: dict | list | str | None = None):
	return event_card("InitiateCheckout")


@frappe.whitelist()
def purchase_count(filters: dict | list | str | None = None):
	return event_card("Purchase")


@frappe.whitelist()
def get_ga4_summary():
	frappe.only_for("System Manager")
	return ga4.get_summary()


def ga4_event_card(metric):
	frappe.only_for("System Manager")
	try:
		totals = ga4.get_summary()["totals"]
	except Exception:
		totals = {}
	return {"value": cint(totals.get(metric)), "fieldtype": "Int"}


@frappe.whitelist()
def ga4_sessions_count(filters: dict | list | str | None = None):
	return ga4_event_card("sessions")


@frappe.whitelist()
def ga4_activeusers_count(filters: dict | list | str | None = None):
	return ga4_event_card("activeUsers")


@frappe.whitelist()
def ga4_pageview_count(filters: dict | list | str | None = None):
	return ga4_event_card("page_view")


@frappe.whitelist()
def ga4_viewitem_count(filters: dict | list | str | None = None):
	return ga4_event_card("view_item")


@frappe.whitelist()
def ga4_addtocart_count(filters: dict | list | str | None = None):
	return ga4_event_card("add_to_cart")


@frappe.whitelist()
def ga4_begincheckout_count(filters: dict | list | str | None = None):
	return ga4_event_card("begin_checkout")


@frappe.whitelist()
def ga4_purchase_count(filters: dict | list | str | None = None):
	return ga4_event_card("purchase")
