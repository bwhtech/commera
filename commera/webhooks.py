import base64
import hashlib
import hmac
import ipaddress
import socket
import time
from urllib.parse import urlsplit

import frappe
import requests
from frappe import _
from frappe.utils import add_to_date, now_datetime
from frappe.utils.data import cstr, get_datetime
from frappe.website.utils import cleanup_page_name

from commera.sdk.events import CommeraEvent

HANDLER = "commera.webhooks.deliver"
SIGNATURE_HEADER = "X-Commera-Hmac-Sha256"
EVENT_HEADER = "X-Commera-Event"
EVENT_ID_HEADER = "X-Commera-Event-Id"
TIMEOUT_SECONDS = 10
SUBSCRIPTIONS_CACHE_KEY = "commera_webhook_subscriptions"
LOG_DOCTYPE = "Commera Webhook Log"
TEST_EVENT = "webhook_test"
FAILURE_LIMIT = 10
FAILURE_WINDOW_HOURS = 24
ALLOW_LOCAL_URLS_CONFIG = "commera_webhooks_allow_local_urls"
REPLAYED_FIELDS = ("webhook", "event", "event_id", "reference_doctype", "reference_name", "is_test")
EVENT_GROUPS = (
	(
		"Orders",
		(
			("order_placed", "Order placed", "A shopper completes checkout"),
			("order_paid", "Order paid", "Payment is captured, including cash on delivery"),
			("order_fulfilled", "Order shipped", "Every item has shipped"),
			("order_delivered", "Order delivered", "The carrier confirms delivery"),
			("order_cancelled", "Order cancelled", "The order is cancelled"),
			("order_refunded", "Order refunded", "All or part of the order is refunded"),
			("order_returned", "Order returned", "All or part of the order comes back"),
			("order_updated", "Order updated", "The order, its address or its status changes"),
		),
	),
	(
		"Catalogue",
		(
			(
				"product_updated",
				"Product updated",
				"A product is added, edited, priced, published or removed",
			),
			("inventory_changed", "Stock changed", "Available stock of a product goes up or down"),
			("collection_updated", "Collection updated", "A collection is added, edited or removed"),
		),
	),
	(
		"Storefront content",
		(
			("page_updated", "Page updated", "A web page is added, edited or removed"),
			("menu_updated", "Menu updated", "The menu, footer or store settings change"),
		),
	),
)
EVENTS = tuple(event for _group, events in EVENT_GROUPS for event, _label, _description in events)


class WebhookDeliveryError(Exception):
	pass


def get_event_groups() -> list[dict]:
	return [
		{
			"label": _(group),
			"events": [
				{"event": event, "label": _(label), "description": _(description)}
				for event, label, description in events
			],
		}
		for group, events in EVENT_GROUPS
	]


def is_subscribed(event: str) -> bool:
	"""Whether an enabled Commera Webhook wants the event. Without one, Commera records no event for it."""
	return event in get_subscriptions()


def get_subscriptions() -> dict[str, list[str]]:
	return frappe.cache.get_value(SUBSCRIPTIONS_CACHE_KEY, generator=read_subscriptions)


def read_subscriptions() -> dict[str, list[str]]:
	webhook = frappe.qb.DocType("Commera Webhook")
	row = frappe.qb.DocType("Commera Webhook Event")
	subscriptions = {}
	for event, name in (
		frappe.qb.from_(row)
		.join(webhook)
		.on(webhook.name == row.parent)
		.select(row.event, webhook.name)
		.where((webhook.enabled == 1) & (row.parenttype == "Commera Webhook"))
		.run()
	):
		subscriptions.setdefault(event, []).append(name)
	return subscriptions


def clear_subscriptions():
	frappe.cache.delete_value(SUBSCRIPTIONS_CACHE_KEY)


def get_url_error(url: str) -> str | None:
	"""Why Commera refuses to post to the URL, or None. Without the site config, only public https URLs pass,
	so a webhook cannot reach the server itself or its private network."""
	parts = urlsplit(url or "")
	if frappe.conf.get(ALLOW_LOCAL_URLS_CONFIG):
		return (
			None
			if parts.scheme in ("https", "http") and parts.hostname
			else _("The URL must start with https:// or http://.")
		)
	if parts.scheme != "https" or not parts.hostname:
		return _("The URL must start with https://.")
	if is_private_host(parts.hostname):
		return _("The URL must point to a public address, not to localhost or a private network.")
	return None


def is_private_host(hostname: str) -> bool:
	try:
		addresses = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
	except (socket.gaierror, UnicodeError):
		# A name that does not resolve reaches nothing, and its post fails on its own.
		return False
	return any(not ipaddress.ip_address(address.split("%")[0]).is_global for address in addresses)


def deliver(event: CommeraEvent):
	"""Post the event to every webhook that wants it and has no Done log for it yet, so a retry only reaches
	the webhooks that failed. A receiver can still see an event twice: dedupe on the X-Commera-Event-Id header."""
	body = frappe.as_json(get_payload(event), indent=None)
	failures = []
	subscribed = get_subscriptions().get(event.name, [])
	# A webhook turned off or unsubscribed since its last attempt is never posted to again.
	fail_event_logs(event.id, keep_webhooks=subscribed)
	for name in subscribed:
		log = get_delivery_log(name, event)
		if log.status == "Done":
			continue
		if send(frappe.get_doc("Commera Webhook", name), log, body):
			save_log(log)
		else:
			save_failed_delivery(log)
			failures.append(f"{name}: {log.error}")
	if failures:
		# The event queue rolls back a handler that raises, which would drop the logs and failure counts.
		# nosemgrep: frappe-manual-commit  # deliveries run in jobs and record each attempt on its own
		frappe.db.commit()
		raise WebhookDeliveryError("; ".join(failures))


def get_delivery_log(webhook: str, event: CommeraEvent):
	name = frappe.db.get_value(
		LOG_DOCTYPE, {"webhook": webhook, "event_id": event.id, "replay_of": ("is", "not set"), "is_test": 0}
	)
	if name:
		return frappe.get_doc(LOG_DOCTYPE, name)
	return new_log(
		webhook=webhook,
		event=event.name,
		event_id=event.id,
		reference_doctype=event.reference_doctype,
		reference_name=event.reference_name,
	)


def new_log(**values):
	return frappe.get_doc({"doctype": LOG_DOCTYPE, **values})


def save_log(log):
	# A log outlives its reference: page_updated fires for a deleted page too.
	log.flags.ignore_links = True
	log.save(ignore_permissions=True)


def save_failed_delivery(log):
	# Imported here: commera.plugin_events imports this module.
	from commera.plugin_events import RETRY_DELAYS_IN_MINUTES

	if log.attempts > len(RETRY_DELAYS_IN_MINUTES):
		log.update({"status": "Failed", "next_retry_at": None})
	else:
		next_retry_at = add_to_date(now_datetime(), minutes=RETRY_DELAYS_IN_MINUTES[log.attempts - 1])
		log.update({"status": "Retrying", "next_retry_at": next_retry_at})
	save_log(log)
	count_failure(log.webhook)


def send(webhook, log, body: str) -> bool:
	"""Post the body signed with the webhook's current secret, and record the attempt on the unsaved log."""
	signature = sign(webhook.get_password("secret"), body)
	started_at = time.monotonic()
	response_code = None
	# Checked again on each post: a name that was public when saved can point inside later.
	error = get_url_error(webhook.url)
	if not error:
		response_code, error = post(webhook.url, log, body, signature)

	log.update(
		{
			"status": "Failed" if error else "Done",
			"next_retry_at": None,
			"attempts": (log.attempts or 0) + 1,
			"response_code": response_code,
			"duration_ms": round((time.monotonic() - started_at) * 1000),
			"error": error,
			"body": body,
			"signature": signature,
		}
	)
	return not error


def post(url: str, log, body: str, signature: str) -> tuple[int | None, str | None]:
	"""Returns the response code and an error. A redirect is an error: following it could reach a private host."""
	try:
		response = requests.post(
			url,
			data=body,
			headers={
				"Content-Type": "application/json",
				SIGNATURE_HEADER: signature,
				EVENT_HEADER: log.event,
				EVENT_ID_HEADER: log.event_id,
			},
			timeout=TIMEOUT_SECONDS,
			allow_redirects=False,
		)
	except requests.RequestException as exception:
		return None, get_error_message(exception)
	if 200 <= response.status_code < 300:
		return response.status_code, None
	return response.status_code, f"{response.status_code} {response.reason or ''}".strip()


def sign(secret: str, body: str) -> str:
	return base64.b64encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()).decode()


def get_error_message(exception: requests.RequestException) -> str:
	if isinstance(exception, requests.Timeout):
		return f"Connection timed out after {TIMEOUT_SECONDS} s"
	if isinstance(exception, requests.ConnectionError) and "refused" in str(exception).lower():
		return "Connection refused"
	return str(exception) or type(exception).__name__


def count_failure(webhook: str):
	"""Count a failed attempt in a fixed 24-hour window, and turn the webhook off at the limit."""
	failure_window_started_at, failed_attempts = frappe.db.get_value(
		"Commera Webhook", webhook, ["failure_window_started_at", "failed_attempts"], for_update=True
	)
	now = now_datetime()
	window_start = add_to_date(now, hours=-FAILURE_WINDOW_HOURS)
	if not failure_window_started_at or get_datetime(failure_window_started_at) < window_start:
		failure_window_started_at, failed_attempts = now, 0
	failed_attempts += 1
	frappe.db.set_value(
		"Commera Webhook",
		webhook,
		{"failure_window_started_at": failure_window_started_at, "failed_attempts": failed_attempts},
		update_modified=False,
	)
	if failed_attempts >= FAILURE_LIMIT:
		turn_off(webhook)


def turn_off(webhook: str):
	frappe.db.set_value("Commera Webhook", webhook, {"enabled": 0, "auto_disabled_at": now_datetime()})
	fail_retrying_logs(webhook)
	clear_subscriptions()
	# Again after the commit, in case another worker cached the webhook as enabled in between.
	frappe.db.after_commit.add(clear_subscriptions)


def fail_event_logs(event_id: str, keep_webhooks: list | None = None, webhook: str | None = None):
	"""Retrying -> Failed for an event's logs that no job will post again: all of them, only one webhook's,
	or all but the kept webhooks'."""
	log = frappe.qb.DocType(LOG_DOCTYPE)
	query = (
		frappe.qb.update(log)
		.set(log.status, "Failed")
		.set(log.next_retry_at, None)
		.where((log.event_id == event_id) & (log.status == "Retrying"))
	)
	if webhook:
		query = query.where(log.webhook == webhook)
	if keep_webhooks:
		query = query.where(log.webhook.notin(keep_webhooks))
	query.run()


def fail_retrying_logs(webhook: str):
	"""The event queue skips a webhook that is off, so its Retrying logs would never finish."""
	log = frappe.qb.DocType(LOG_DOCTYPE)
	(
		frappe.qb.update(log)
		.set(log.status, "Failed")
		.set(log.next_retry_at, None)
		.where((log.webhook == webhook) & (log.status == "Retrying"))
	).run()


def send_test(webhook) -> str:
	"""Post a webhook_test event now. Returns the log name. A test never counts towards the failure limit."""
	event = CommeraEvent(
		id=f"{TEST_EVENT}-{frappe.generate_hash(length=10)}",
		name=TEST_EVENT,
		reference_doctype=None,
		reference_name=None,
		data={"test": True},
		created_at=now_datetime(),
	)
	log = new_log(webhook=webhook.name, event=event.name, event_id=event.id, is_test=1)
	return save_one_off(webhook, log, frappe.as_json(get_payload(event), indent=None))


def replay(original) -> str:
	"""Post a logged body again to its webhook's current URL, signed with the current secret. Returns the new
	log name. A replay never counts towards the failure limit."""
	log = new_log(replay_of=original.name, **{field: original.get(field) for field in REPLAYED_FIELDS})
	return save_one_off(frappe.get_doc("Commera Webhook", original.webhook), log, original.body)


def save_one_off(webhook, log, body: str) -> str:
	send(webhook, log, body)
	save_log(log)
	return log.name


def retry_failing_logs(webhook: str) -> int:
	"""Queue the event delivery behind each Retrying log of the webhook to run now. Returns how many."""
	# Imported here: commera.plugin_events imports this module.
	from commera.plugin_events import queue_delivery_now

	log = frappe.qb.DocType(LOG_DOCTYPE)
	commera_event = frappe.qb.DocType("Commera Event")
	delivery = frappe.qb.DocType("Commera Event Delivery")
	deliveries = (
		frappe.qb.from_(log)
		.join(commera_event)
		.on(commera_event.event_key == log.event_id)
		.join(delivery)
		.on(delivery.parent == commera_event.name)
		.select(delivery.name, log.event_id)
		.distinct()
		.where(
			(log.webhook == webhook)
			& (log.status == "Retrying")
			& (delivery.handler == HANDLER)
			& (delivery.status != "Running")
		)
		.run(as_dict=True)
	)
	queued = 0
	for row in deliveries:
		if queue_delivery_now(row.name):
			queued += 1
		else:
			# The delivery already finished, so nothing will post this log again.
			fail_event_logs(row.event_id, webhook=webhook)
	frappe.db.set_value(
		LOG_DOCTYPE, {"webhook": webhook, "status": "Retrying"}, "next_retry_at", now_datetime()
	)
	return queued


def get_payload(event: CommeraEvent) -> dict:
	return {
		"id": event.id,
		"event": event.name,
		"reference_doctype": event.reference_doctype,
		"reference_name": event.reference_name,
		"created_at": str(event.created_at),
		"data": {**event.data, **get_storefront_data(event)},
	}


def get_storefront_data(event: CommeraEvent) -> dict:
	"""The storefront handles an event touches, so a headless storefront can expire just those pages."""
	if event.name == "product_updated":
		return {"handles": get_product_handles({"item_style": event.data.get("item_code")})}
	if event.name == "inventory_changed":
		# The stock event names its item as the reference, not in its data.
		return {"handles": get_size_handles(cstr(event.reference_name))}
	if event.name == "collection_updated":
		return {"handle": cleanup_page_name(event.reference_name).replace("_", "-")}
	return {}


def get_product_handles(filters: dict) -> list[str]:
	return frappe.get_all("Style Attribute Variant", filters=filters, pluck="route", order_by="route asc")


def get_size_handles(item_code: str) -> list[str]:
	variants = frappe.get_all(
		"Color Size Item",
		filters={"item_code": item_code, "parenttype": "Style Attribute Variant"},
		pluck="parent",
	)
	return get_product_handles({"name": ("in", variants)}) if variants else []
