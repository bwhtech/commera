import base64
import hashlib
import hmac

import frappe
import requests
from frappe.utils.data import cstr
from frappe.website.utils import cleanup_page_name

from commera.sdk.events import CommeraEvent

HANDLER = "commera.webhooks.deliver"
SIGNATURE_HEADER = "X-Commera-Hmac-Sha256"
EVENT_HEADER = "X-Commera-Event"
EVENT_ID_HEADER = "X-Commera-Event-Id"
TIMEOUT_SECONDS = 10
SUBSCRIPTIONS_CACHE_KEY = "commera_webhook_subscriptions"


class WebhookDeliveryError(Exception):
	pass


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


def deliver(event: CommeraEvent):
	"""Post the event to every webhook that wants it. One failure retries the event for all of them, so a
	receiver can see an event twice: dedupe on the X-Commera-Event-Id header."""
	body = frappe.as_json(get_payload(event), indent=None)
	failures = []
	for name in get_subscriptions().get(event.name, []):
		webhook = frappe.get_doc("Commera Webhook", name)
		try:
			post(webhook, event, body)
		except requests.RequestException as error:
			failures.append(f"{name}: {error}")
	if failures:
		raise WebhookDeliveryError("; ".join(failures))


def post(webhook, event: CommeraEvent, body: str):
	secret = webhook.get_password("secret")
	signature = base64.b64encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()).decode()
	response = requests.post(
		webhook.url,
		data=body,
		headers={
			"Content-Type": "application/json",
			SIGNATURE_HEADER: signature,
			EVENT_HEADER: event.name,
			EVENT_ID_HEADER: event.id,
		},
		timeout=TIMEOUT_SECONDS,
	)
	response.raise_for_status()


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
