import frappe
from frappe.query_builder import Case, Order
from frappe.query_builder.functions import Count, Max, Sum
from frappe.utils.data import cint

from commera import webhooks
from commera.commera_ecommerce.doctype.commera_webhook.commera_webhook import generate_secret

DOCTYPE = "Commera Webhook"
MAX_PAGE_LENGTH = 100
LOG_FIELDS = (
	"name",
	"event",
	"event_id",
	"reference_doctype",
	"reference_name",
	"status",
	"attempts",
	"response_code",
	"duration_ms",
	"error",
	"next_retry_at",
	"replay_of",
	"is_test",
	"creation",
	"modified",
)


@frappe.whitelist()
def get_event_groups() -> list[dict]:
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)
	return webhooks.get_event_groups()


@frappe.whitelist()
def get_webhooks() -> list[dict]:
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)
	rows = frappe.get_list(
		DOCTYPE, fields=["name", "url", "enabled", "auto_disabled_at"], order_by="creation desc"
	)
	names = [row.name for row in rows]
	events = get_subscribed_events(names)
	activity = get_log_activity(names)
	return [
		{
			"name": row.name,
			"url": row.url,
			"enabled": bool(row.enabled),
			"events": events.get(row.name, []),
			"auto_disabled_at": row.auto_disabled_at,
			**activity.get(row.name, {"is_failing": False, "last_sent_at": None}),
		}
		for row in rows
	]


def get_subscribed_events(webhook_names: list[str]) -> dict[str, list[str]]:
	events = {}
	for row in frappe.get_all(
		"Commera Webhook Event",
		filters={"parenttype": DOCTYPE, "parent": ("in", webhook_names or [""])},
		fields=["parent", "event"],
		order_by="idx asc",
	):
		events.setdefault(row.parent, []).append(row.event)
	return events


def get_log_activity(webhook_names: list[str]) -> dict[str, dict]:
	log = frappe.qb.DocType(webhooks.LOG_DOCTYPE)
	rows = (
		frappe.qb.from_(log)
		.select(
			log.webhook,
			Max(log.modified).as_("last_sent_at"),
			Sum(Case().when(log.status == "Retrying", 1).else_(0)).as_("failing_count"),
		)
		.where(log.webhook.isin(webhook_names or [""]))
		.groupby(log.webhook)
		.run(as_dict=True)
	)
	return {
		row.webhook: {"is_failing": cint(row.failing_count) > 0, "last_sent_at": row.last_sent_at}
		for row in rows
	}


@frappe.whitelist()
def get_webhook(name: str) -> dict:
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	return get_webhook_details(doc)


def get_webhook_details(doc) -> dict:
	activity = get_log_activity([doc.name]).get(doc.name, {"last_sent_at": None})
	failing_count = frappe.db.count(webhooks.LOG_DOCTYPE, {"webhook": doc.name, "status": "Retrying"})
	return {
		"name": doc.name,
		"url": doc.url,
		"enabled": bool(doc.enabled),
		"events": [row.event for row in doc.events],
		"auto_disabled_at": doc.auto_disabled_at,
		"failed_attempts": cint(doc.failed_attempts),
		"failure_limit": webhooks.FAILURE_LIMIT,
		"failing_count": failing_count,
		"last_error": frappe.db.get_value(
			webhooks.LOG_DOCTYPE,
			{"webhook": doc.name, "error": ("is", "set")},
			"error",
			order_by="modified desc",
		),
		"secret_hint": doc.get_password("secret")[-4:],
		"is_failing": failing_count > 0,
		"last_sent_at": activity["last_sent_at"],
	}


@frappe.whitelist()
def get_webhook_logs(webhook: str, start: int = 0, page_length: int = 20) -> dict:
	frappe.has_permission(DOCTYPE, doc=webhook, ptype="read", throw=True)
	log = frappe.qb.DocType(webhooks.LOG_DOCTYPE)
	rows = (
		frappe.qb.from_(log)
		.select(*LOG_FIELDS)
		.where(log.webhook == webhook)
		.orderby(log.creation, order=Order.desc)
		.limit(min(cint(page_length), MAX_PAGE_LENGTH))
		.offset(cint(start))
		.run(as_dict=True)
	)
	total = frappe.qb.from_(log).select(Count("*")).where(log.webhook == webhook).run()[0][0]
	return {"rows": [as_log_row(row) for row in rows], "total": total}


def as_log_row(row) -> dict:
	return {**{field: row.get(field) for field in LOG_FIELDS}, "is_test": bool(row.get("is_test"))}


@frappe.whitelist()
def get_webhook_log(name: str) -> dict:
	log = get_log(name, "read")
	return {
		**as_log_row(log),
		"body": log.body,
		"headers": [
			[webhooks.EVENT_HEADER, log.event],
			[webhooks.EVENT_ID_HEADER, log.event_id],
			[webhooks.SIGNATURE_HEADER, log.signature],
		],
	}


def get_log(name: str, ptype: str):
	log = frappe.get_doc(webhooks.LOG_DOCTYPE, name)
	frappe.has_permission(DOCTYPE, doc=log.webhook, ptype=ptype, throw=True)
	return log


@frappe.whitelist(methods=["POST"])
def create_webhook(url: str, events: list[str] | str) -> dict:
	frappe.has_permission(DOCTYPE, ptype="create", throw=True)
	secret = generate_secret()
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"url": url,
			"secret": secret,
			"events": [{"event": event} for event in frappe.parse_json(events) or []],
		}
	).insert()
	return {"name": doc.name, "secret": secret}


@frappe.whitelist(methods=["POST"])
def update_webhook(
	name: str, url: str | None = None, enabled: bool | None = None, events: list[str] | str | None = None
) -> dict:
	doc = get_writable_webhook(name)
	if url is not None:
		doc.url = url
	if enabled is not None:
		doc.enabled = cint(enabled)
	if events is not None:
		doc.set("events", [{"event": event} for event in frappe.parse_json(events) or []])
	doc.save()
	return get_webhook_details(doc)


def get_writable_webhook(name: str):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	return doc


@frappe.whitelist(methods=["POST"])
def delete_webhook(name: str) -> None:
	frappe.delete_doc(DOCTYPE, name)


@frappe.whitelist(methods=["POST"])
def reveal_secret(name: str) -> dict:
	return {"secret": get_writable_webhook(name).get_password("secret")}


@frappe.whitelist(methods=["POST"])
def rotate_secret(name: str) -> dict:
	doc = get_writable_webhook(name)
	doc.secret = generate_secret()
	secret = doc.secret
	doc.save()
	return {"secret": secret}


@frappe.whitelist(methods=["POST"])
def send_test(name: str) -> dict:
	return get_log_row(webhooks.send_test(get_writable_webhook(name)))


@frappe.whitelist(methods=["POST"])
def replay(log: str) -> dict:
	return get_log_row(webhooks.replay(get_log(log, "write")))


def get_log_row(name: str) -> dict:
	return as_log_row(frappe.db.get_value(webhooks.LOG_DOCTYPE, name, LOG_FIELDS, as_dict=True))


@frappe.whitelist(methods=["POST"])
def retry_failed(webhook: str) -> dict:
	get_writable_webhook(webhook)
	return {"count": webhooks.retry_failing_logs(webhook)}
