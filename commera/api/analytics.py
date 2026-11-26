import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cint, cstr, flt

from commera.analytics import events, facebook, ga4

CLIENT_EVENTS = ("page_view", "view_item", "add_to_cart", "begin_checkout")


def get_capture_payload():
	payload = frappe.request.get_json(silent=True) if frappe.request else None
	if not isinstance(payload, dict):
		payload = frappe.form_dict
	return payload


# nosemgrep: frappe-semgrep-rules.rules.security.guest-whitelisted-method  # anonymous beacon: validated, clamped, rate-limited
@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=600, seconds=60)
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

	# Direct parameterized INSERT avoids full ORM Document/meta overhead on high-frequency guest beacons.
	now = frappe.utils.now()
	owner = frappe.session.user or "Guest"
	frappe.db.sql(
		"""
		INSERT INTO `tabStorefront Analytics Event` (
			name, creation, modified, modified_by, owner, docstatus, idx,
			event, session_id, visitor_user, device, item_code, qty, value,
			currency, path, referrer, utm_source, utm_medium, utm_campaign,
			utm_term, utm_content, items_json
		) VALUES (
			%s, %s, %s, %s, %s, 0, 0,
			%s, %s, %s, %s, %s, %s, %s,
			%s, %s, %s, %s, %s, %s,
			%s, %s, %s
		)
		""",
		(
			frappe.generate_hash(length=10),
			now,
			now,
			owner,
			owner,
			payload.get("event"),
			events.clip(payload.get("session_id"), 64),
			events.get_visitor_user(),
			events.get_device(events.get_user_agent()),
			item_code or None,
			cint(payload.get("qty")),
			flt(payload.get("value")),
			events.clip(payload.get("currency"), 8),
			events.clip(payload.get("path"), 255),
			events.clip(payload.get("referrer"), 255),
			events.clip(payload.get("utm_source"), 140),
			events.clip(payload.get("utm_medium"), 140),
			events.clip(payload.get("utm_campaign"), 140),
			events.clip(payload.get("utm_term"), 140),
			events.clip(payload.get("utm_content"), 140),
			events.get_items_snapshot(payload.get("items")),
		),
	)


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
