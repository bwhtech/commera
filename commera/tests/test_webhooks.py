import base64
import hashlib
import hmac
from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.utils import now_datetime

from commera import plugin_events
from commera.sdk.events import CommeraEvent
from commera.tests.test_product_details import ProductDetailPriceTestCase
from commera.webhooks import (
	EVENT_HEADER,
	EVENT_ID_HEADER,
	HANDLER,
	SIGNATURE_HEADER,
	WebhookDeliveryError,
	clear_subscriptions,
	deliver,
)

SECRET = "zz-webhook-secret"


class TestWebhooks(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		# The class rolls back once at the end, so each test starts with no webhooks of its own.
		frappe.db.delete("Commera Webhook Event", {"parenttype": "Commera Webhook"})
		frappe.db.delete("Commera Webhook")
		clear_subscriptions()
		self.addCleanup(clear_subscriptions)

	def make_webhook(self, events: list[str], enabled: int = 1, url: str = "https://store.example.com/hook"):
		return frappe.get_doc(
			{
				"doctype": "Commera Webhook",
				"title": f"ZZ Hook {frappe.generate_hash(length=6)}",
				"url": url,
				"secret": SECRET,
				"enabled": enabled,
				"events": [{"event": event} for event in events],
			}
		).insert(ignore_permissions=True)

	def make_event(self, name: str, data: dict) -> CommeraEvent:
		return CommeraEvent(
			id=f"{name}-zz",
			name=name,
			reference_doctype="Item",
			reference_name="ZZ",
			data=data,
			created_at=now_datetime(),
		)

	def test_no_event_is_recorded_until_a_webhook_subscribes(self):
		self.assertNotIn(HANDLER, plugin_events.get_handlers("commera_events", "product_updated"))

		webhook = self.make_webhook(["product_updated"])

		self.assertIn(HANDLER, plugin_events.get_handlers("commera_events", "product_updated"))
		self.assertNotIn(HANDLER, plugin_events.get_handlers("commera_events", "order_paid"))
		webhook.enabled = 0
		webhook.save()
		self.assertNotIn(HANDLER, plugin_events.get_handlers("commera_events", "product_updated"))

	def test_a_disabled_webhook_subscribes_to_nothing(self):
		self.make_webhook(["menu_updated"], enabled=0)

		self.assertNotIn(HANDLER, plugin_events.get_handlers("commera_events", "menu_updated"))

	def test_an_event_is_posted_signed_with_the_product_handles(self):
		route = self.make_priced_variant("HOOK", default_rate=10)
		item_style = frappe.db.get_value("Style Attribute Variant", {"route": route}, "item_style")
		self.make_webhook(["product_updated"])

		with patch("commera.webhooks.requests.post") as post:
			post.return_value = MagicMock(raise_for_status=MagicMock())
			deliver(self.make_event("product_updated", {"item_code": item_style, "changed": ["price"]}))

		body, headers = post.call_args.kwargs["data"], post.call_args.kwargs["headers"]
		expected = base64.b64encode(
			hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest()
		).decode()
		self.assertEqual(headers[SIGNATURE_HEADER], expected)
		self.assertEqual(
			(headers[EVENT_HEADER], headers[EVENT_ID_HEADER]), ("product_updated", "product_updated-zz")
		)
		payload = frappe.parse_json(body)
		# The test factory styles every product on one template, so each one shares its handles.
		self.assertIn(route, payload["data"]["handles"])
		self.assertEqual(payload["data"]["changed"], ["price"])

	def test_a_stock_event_names_the_products_that_sell_the_item(self):
		route = self.make_priced_variant("STOCK", default_rate=10)
		variant = frappe.db.get_value("Style Attribute Variant", {"route": route})
		item_code = frappe.db.get_value("Color Size Item", {"parent": variant}, "item_code")
		self.make_webhook(["inventory_changed"])
		event = CommeraEvent(
			id="inventory-zz",
			name="inventory_changed",
			reference_doctype="Item",
			reference_name=item_code,
			data={"available_qty": 3},
			created_at=now_datetime(),
		)

		with patch("commera.webhooks.requests.post") as post:
			post.return_value = MagicMock(raise_for_status=MagicMock())
			deliver(event)

		self.assertEqual(frappe.parse_json(post.call_args.kwargs["data"])["data"]["handles"], [route])

	def test_a_failed_post_raises_so_the_event_is_retried(self):
		self.make_webhook(["menu_updated"])
		self.make_webhook(["menu_updated"], url="https://down.example.com/hook")

		def post(url, **kwargs):
			if "down" in url:
				raise requests.ConnectionError("refused")
			return MagicMock(raise_for_status=MagicMock())

		with patch("commera.webhooks.requests.post", side_effect=post) as mock_post:
			with self.assertRaisesRegex(WebhookDeliveryError, "refused"):
				deliver(self.make_event("menu_updated", {}))
		self.assertEqual(mock_post.call_count, 2)

	def test_storefront_changes_wait_for_a_subscriber_and_batch_per_transaction(self):
		frappe.local.flags.pop(plugin_events.CHANGED_STOREFRONT_FLAG, None)
		self.addCleanup(frappe.local.flags.pop, plugin_events.CHANGED_STOREFRONT_FLAG, None)
		plugin_events.add_storefront_change("menu_updated", "Commera Settings", "Commera Settings")
		self.assertIsNone(frappe.local.flags.get(plugin_events.CHANGED_STOREFRONT_FLAG))

		self.make_webhook(["menu_updated", "collection_updated"])
		plugin_events.add_storefront_change("menu_updated", "Commera Settings", "Commera Settings")
		plugin_events.add_storefront_change("menu_updated", "Commera Settings", "Commera Settings")
		plugin_events.on_item_group_change(frappe.get_doc("Item Group", self.item_group))

		self.assertEqual(
			set(frappe.local.flags[plugin_events.CHANGED_STOREFRONT_FLAG]),
			{
				("menu_updated", "Commera Settings", "Commera Settings"),
				("collection_updated", "Item Group", self.item_group),
			},
		)

	def test_an_event_can_be_listed_once(self):
		with self.assertRaisesRegex(frappe.ValidationError, "listed once"):
			self.make_webhook(["page_updated", "page_updated"])
