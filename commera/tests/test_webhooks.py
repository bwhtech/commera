import base64
import hashlib
import hmac
from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.core.doctype.user_permission.test_user_permission import create_user
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from commera import plugin_events
from commera.api.admin import webhooks as webhooks_api
from commera.roles import COMMERA_ADMIN, COMMERA_USER, add_commera_roles
from commera.sdk import STORE_ORDER_TYPE
from commera.sdk.events import HANDLER_HOOKS, CommeraEvent
from commera.tests.test_admin_orders import make_test_sales_order
from commera.tests.test_product_details import ProductDetailPriceTestCase
from commera.utils import update_sales_order_ecommerce_status
from commera.webhooks import (
	ALLOW_LOCAL_URLS_CONFIG,
	EVENT_HEADER,
	EVENT_ID_HEADER,
	EVENTS,
	FAILURE_LIMIT,
	HANDLER,
	LOG_DOCTYPE,
	SIGNATURE_HEADER,
	WebhookDeliveryError,
	clear_subscriptions,
	deliver,
	get_subscriptions,
)

SECRET = "zz-webhook-secret"
WEBHOOK_ADMIN = "zz-webhook-admin@example.com"
WEBHOOK_PICKER = "zz-webhook-picker@example.com"
DOWN_URL = "https://down.example.com/hook"


def reset_webhooks(test_case):
	# The class rolls back once at the end, so each test starts with no webhooks of its own.
	frappe.db.delete(LOG_DOCTYPE)
	frappe.db.delete("Commera Webhook Event", {"parenttype": "Commera Webhook"})
	frappe.db.delete("Commera Webhook")
	clear_subscriptions()
	test_case.addCleanup(clear_subscriptions)


def make_webhook(
	events: list[str], enabled: int = 1, url: str = "https://store.example.com/hook", secret=SECRET
):
	return frappe.get_doc(
		{
			"doctype": "Commera Webhook",
			"url": url,
			"secret": secret,
			"enabled": enabled,
			"events": [{"event": event} for event in events],
		}
	).insert(ignore_permissions=True)


def make_response(status_code: int = 200, reason: str = "OK"):
	return MagicMock(status_code=status_code, reason=reason)


def post_unless_down(url, **kwargs):
	if url == DOWN_URL:
		raise requests.ConnectionError("[Errno 111] Connection refused")
	return make_response()


def sign(secret: str, body: str) -> str:
	return base64.b64encode(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()).decode()


def get_logs(webhook: str) -> list:
	return frappe.get_all(LOG_DOCTYPE, filters={"webhook": webhook}, fields=["*"], order_by="creation asc")


class TestWebhooks(ProductDetailPriceTestCase):
	def setUp(self):
		super().setUp()
		reset_webhooks(self)

	def make_event(self, name: str, data: dict, event_id: str | None = None) -> CommeraEvent:
		return CommeraEvent(
			id=event_id or f"{name}-zz",
			name=name,
			reference_doctype="Item",
			reference_name="ZZ",
			data=data,
			created_at=now_datetime(),
		)

	def deliver_and_fail(self, event: CommeraEvent, post=post_unless_down):
		# deliver commits its logs before it raises, which would commit the test's fixtures with them.
		with patch("commera.webhooks.requests.post", side_effect=post), patch.object(frappe.db, "commit"):
			with self.assertRaises(WebhookDeliveryError):
				deliver(event)

	def test_no_event_is_recorded_until_a_webhook_subscribes(self):
		self.assertNotIn(HANDLER, plugin_events.get_handlers("commera_events", "product_updated"))

		webhook = make_webhook(["product_updated"])

		self.assertIn(HANDLER, plugin_events.get_handlers("commera_events", "product_updated"))
		self.assertNotIn(HANDLER, plugin_events.get_handlers("commera_events", "order_paid"))
		webhook.enabled = 0
		webhook.save()
		self.assertNotIn(HANDLER, plugin_events.get_handlers("commera_events", "product_updated"))

	def test_a_disabled_webhook_subscribes_to_nothing(self):
		make_webhook(["menu_updated"], enabled=0)

		self.assertNotIn(HANDLER, plugin_events.get_handlers("commera_events", "menu_updated"))

	def test_webhooks_are_offered_exactly_the_events_they_get(self):
		options = frappe.get_meta("Commera Webhook Event").get_field("event").options.split("\n")
		self.assertEqual(options, list(EVENTS))
		self.assertEqual(
			sorted(
				event for event, handlers in frappe.get_hooks("commera_events").items() if HANDLER in handlers
			),
			sorted(EVENTS),
		)
		self.assertLessEqual(set(EVENTS), set(HANDLER_HOOKS["commera_events"]))
		self.assertNotIn("cart_created", EVENTS)

	def test_an_event_is_posted_signed_with_the_product_handles(self):
		route = self.make_priced_variant("HOOK", default_rate=10)
		item_style = frappe.db.get_value("Style Attribute Variant", {"route": route}, "item_style")
		make_webhook(["product_updated"])

		with patch("commera.webhooks.requests.post", return_value=make_response()) as post:
			deliver(self.make_event("product_updated", {"item_code": item_style, "changed": ["price"]}))

		body, headers = post.call_args.kwargs["data"], post.call_args.kwargs["headers"]
		self.assertEqual(headers[SIGNATURE_HEADER], sign(SECRET, body))
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
		make_webhook(["inventory_changed"])
		event = CommeraEvent(
			id="inventory-zz",
			name="inventory_changed",
			reference_doctype="Item",
			reference_name=item_code,
			data={"available_qty": 3},
			created_at=now_datetime(),
		)

		with patch("commera.webhooks.requests.post", return_value=make_response()) as post:
			deliver(event)

		self.assertEqual(frappe.parse_json(post.call_args.kwargs["data"])["data"]["handles"], [route])

	def test_a_delivery_is_logged_with_what_was_posted(self):
		webhook = make_webhook(["menu_updated"])

		with patch("commera.webhooks.requests.post", return_value=make_response()) as post:
			deliver(self.make_event("menu_updated", {}))

		[log] = get_logs(webhook.name)
		self.assertEqual((log.status, log.attempts, log.response_code), ("Done", 1, 200))
		self.assertEqual((log.event, log.event_id, log.is_test), ("menu_updated", "menu_updated-zz", 0))
		self.assertEqual(log.body, post.call_args.kwargs["data"])
		self.assertEqual(log.signature, post.call_args.kwargs["headers"][SIGNATURE_HEADER])
		self.assertIsNone(log.error)

	def test_a_retry_only_posts_to_the_webhooks_that_failed(self):
		working = make_webhook(["menu_updated"])
		down = make_webhook(["menu_updated"], url=DOWN_URL)
		event = self.make_event("menu_updated", {})

		self.deliver_and_fail(event)

		[working_log], [down_log] = get_logs(working.name), get_logs(down.name)
		self.assertEqual(working_log.status, "Done")
		self.assertEqual((down_log.status, down_log.attempts), ("Retrying", 1))
		self.assertEqual(down_log.error, "Connection refused")
		self.assertGreater(down_log.next_retry_at, now_datetime())
		self.assertEqual(frappe.db.get_value("Commera Webhook", down.name, "failed_attempts"), 1)

		with patch("commera.webhooks.requests.post", side_effect=post_unless_down) as post:
			with patch.object(frappe.db, "commit"), self.assertRaises(WebhookDeliveryError):
				deliver(event)

		self.assertEqual([call.args[0] for call in post.call_args_list], [DOWN_URL])
		self.assertEqual(get_logs(down.name)[0].attempts, 2)
		self.assertEqual(len(get_logs(working.name)), 1)

	def test_the_last_retry_fails_the_log(self):
		down = make_webhook(["menu_updated"], url=DOWN_URL)
		event = self.make_event("menu_updated", {})
		for _attempt in range(len(plugin_events.RETRY_DELAYS_IN_MINUTES) + 1):
			self.deliver_and_fail(event)

		[log] = get_logs(down.name)
		self.assertEqual((log.status, log.next_retry_at), ("Failed", None))

	def test_the_failure_limit_turns_the_webhook_off_and_fails_its_retries(self):
		down = make_webhook(["menu_updated", "page_updated"], url=DOWN_URL)
		self.deliver_and_fail(self.make_event("page_updated", {}))
		frappe.db.set_value("Commera Webhook", down.name, "failed_attempts", FAILURE_LIMIT - 1)

		self.deliver_and_fail(
			self.make_event("menu_updated", {}),
			post=lambda url, **kwargs: make_response(503, "Service Unavailable"),
		)

		down.reload()
		self.assertFalse(down.enabled)
		self.assertIsNotNone(down.auto_disabled_at)
		self.assertNotIn(down.name, get_subscriptions().get("menu_updated", []))
		logs = {log.event: log for log in get_logs(down.name)}
		self.assertEqual({log.status for log in logs.values()}, {"Failed"})
		self.assertEqual({log.next_retry_at for log in logs.values()}, {None})
		self.assertEqual(logs["menu_updated"].error, "503 Service Unavailable")
		self.assertEqual(logs["page_updated"].error, "Connection refused")

	def test_turning_a_webhook_off_fails_its_retries(self):
		down = make_webhook(["menu_updated"], url=DOWN_URL)
		self.deliver_and_fail(self.make_event("menu_updated", {}))

		webhooks_api.update_webhook(down.name, enabled=False)

		[log] = get_logs(down.name)
		self.assertEqual((log.status, log.next_retry_at), ("Failed", None))
		down.reload()
		self.assertIsNone(down.auto_disabled_at)

	def test_failures_older_than_a_day_start_a_new_window(self):
		down = make_webhook(["menu_updated"], url=DOWN_URL)
		frappe.db.set_value(
			"Commera Webhook",
			down.name,
			{
				"failed_attempts": FAILURE_LIMIT - 1,
				"failure_window_started_at": add_to_date(now_datetime(), hours=-25),
			},
		)

		self.deliver_and_fail(self.make_event("menu_updated", {}))

		down.reload()
		self.assertTrue(down.enabled)
		self.assertEqual(down.failed_attempts, 1)

	def test_turning_a_webhook_on_clears_its_failures(self):
		webhook = make_webhook(["menu_updated"])
		frappe.db.set_value(
			"Commera Webhook",
			webhook.name,
			{
				"enabled": 0,
				"auto_disabled_at": now_datetime(),
				"failed_attempts": FAILURE_LIMIT,
				"failure_window_started_at": now_datetime(),
			},
		)

		details = webhooks_api.update_webhook(webhook.name, enabled=True)

		webhook.reload()
		self.assertEqual(
			(
				webhook.enabled,
				webhook.auto_disabled_at,
				webhook.failed_attempts,
				webhook.failure_window_started_at,
			),
			(1, None, 0, None),
		)
		self.assertEqual((details["enabled"], details["auto_disabled_at"]), (True, None))

	def test_a_secret_is_generated_and_can_be_rotated(self):
		webhook = make_webhook(["menu_updated"], secret=None)
		secret = webhook.get_password("secret")
		self.assertRegex(secret, r"^whsec_[0-9a-f]{32}$")

		rotated = webhooks_api.rotate_secret(webhook.name)["secret"]

		self.assertNotEqual(rotated, secret)
		self.assertEqual(webhooks_api.reveal_secret(webhook.name), {"secret": rotated})
		self.assertEqual(webhooks_api.get_webhook(webhook.name)["secret_hint"], rotated[-4:])

	def test_a_replay_posts_the_logged_body_signed_with_the_current_secret(self):
		webhook = make_webhook(["menu_updated"])
		with patch("commera.webhooks.requests.post", return_value=make_response()):
			deliver(self.make_event("menu_updated", {}))
		[original] = get_logs(webhook.name)
		secret = webhooks_api.rotate_secret(webhook.name)["secret"]

		with patch("commera.webhooks.requests.post", return_value=make_response(500, "Server Error")) as post:
			row = webhooks_api.replay(original.name)

		headers = post.call_args.kwargs["headers"]
		self.assertEqual(post.call_args.kwargs["data"], original.body)
		self.assertEqual(headers[SIGNATURE_HEADER], sign(secret, original.body))
		self.assertEqual(headers[EVENT_ID_HEADER], original.event_id)
		self.assertEqual(
			(row["replay_of"], row["status"], row["error"]), (original.name, "Failed", "500 Server Error")
		)
		self.assertEqual(frappe.db.get_value("Commera Webhook", webhook.name, "failed_attempts"), 0)

	def test_a_test_is_logged_and_never_counts_as_a_failure(self):
		webhook = make_webhook(["menu_updated"], url=DOWN_URL)

		with patch("commera.webhooks.requests.post", side_effect=post_unless_down) as post:
			row = webhooks_api.send_test(webhook.name)

		payload = frappe.parse_json(post.call_args.kwargs["data"])
		self.assertEqual((payload["event"], payload["data"]), ("webhook_test", {"test": True}))
		self.assertTrue(payload["id"].startswith("webhook_test-"))
		self.assertIsNone(payload["reference_doctype"])
		self.assertEqual((row["is_test"], row["status"], row["event_id"]), (True, "Failed", payload["id"]))
		self.assertEqual(frappe.db.get_value("Commera Webhook", webhook.name, "failed_attempts"), 0)

	def test_retry_failed_queues_the_event_now(self):
		webhook = make_webhook(["menu_updated"], url=DOWN_URL)
		plugin_events.fire_event("menu_updated", "Commera Settings", "Commera Settings", repeatable=True)
		event_key = frappe.db.get_value(
			"Commera Event", {"event": "menu_updated"}, "name", order_by="creation desc"
		)
		self.deliver_and_fail(self.make_event("menu_updated", {}, event_id=event_key))
		delivery = frappe.db.get_value("Commera Event Delivery", {"parent": event_key, "handler": HANDLER})
		frappe.db.set_value(
			"Commera Event Delivery", delivery, "next_retry_at", add_to_date(now_datetime(), hours=1)
		)

		with patch.object(plugin_events, "enqueue_app_deliveries") as enqueue:
			self.assertEqual(webhooks_api.retry_failed(webhook.name), {"count": 1})

		self.assertLessEqual(
			frappe.db.get_value("Commera Event Delivery", delivery, "next_retry_at"), now_datetime()
		)
		enqueue.assert_called_once_with("commera", "Commera Settings", "Commera Settings", "menu_updated")

	def test_a_webhook_unsubscribed_since_its_last_attempt_fails_its_retrying_log(self):
		down = make_webhook(["menu_updated"], url=DOWN_URL)
		event = self.make_event("menu_updated", {})
		self.deliver_and_fail(event)
		down.reload()
		down.events = []
		down.append("events", {"event": "page_updated"})
		down.save(ignore_permissions=True)
		clear_subscriptions()

		deliver(event)

		[log] = get_logs(down.name)
		self.assertEqual((log.status, log.next_retry_at), ("Failed", None))

	def retrying_log_and_delivery(self, webhook):
		plugin_events.fire_event("menu_updated", "Commera Settings", "Commera Settings", repeatable=True)
		event_key = frappe.db.get_value(
			"Commera Event", {"event": "menu_updated"}, "name", order_by="creation desc"
		)
		self.deliver_and_fail(self.make_event("menu_updated", {}, event_id=event_key))
		self.assertEqual(get_logs(webhook.name)[0].status, "Retrying")
		return event_key, frappe.db.get_value(
			"Commera Event Delivery", {"parent": event_key, "handler": HANDLER}
		)

	def test_retry_failed_fails_a_log_whose_delivery_already_finished(self):
		webhook = make_webhook(["menu_updated"], url=DOWN_URL)
		_event_key, delivery = self.retrying_log_and_delivery(webhook)
		frappe.db.set_value("Commera Event Delivery", delivery, "status", "Done")

		with patch.object(plugin_events, "enqueue_app_deliveries") as enqueue:
			self.assertEqual(webhooks_api.retry_failed(webhook.name), {"count": 0})

		enqueue.assert_not_called()
		self.assertEqual(frappe.db.get_value("Commera Event Delivery", delivery, "status"), "Done")
		self.assertEqual(get_logs(webhook.name)[0].status, "Failed")

	def test_a_delivery_that_runs_out_of_retries_fails_its_retrying_logs(self):
		webhook = make_webhook(["menu_updated"], url=DOWN_URL)
		event_key, delivery = self.retrying_log_and_delivery(webhook)
		frappe.db.set_value("Commera Event Delivery", delivery, "status", "Running")
		row = frappe._dict(
			name=delivery,
			attempts=len(plugin_events.RETRY_DELAYS_IN_MINUTES),
			handler=HANDLER,
			event_key=event_key,
		)

		self.assertTrue(plugin_events.save_failed_attempt(row, None))

		self.assertEqual(frappe.db.get_value("Commera Event Delivery", delivery, "status"), "Failed")
		self.assertEqual(get_logs(webhook.name)[0].status, "Failed")

	def test_the_admin_api_lists_and_describes_webhooks(self):
		created = webhooks_api.create_webhook(
			"https://store.example.com/hook", ["menu_updated", "page_updated"]
		)
		self.assertEqual(webhooks_api.reveal_secret(created["name"]), {"secret": created["secret"]})
		self.deliver_and_fail(
			self.make_event("menu_updated", {}),
			post=lambda url, **kwargs: make_response(503, "Service Unavailable"),
		)

		[webhook] = webhooks_api.get_webhooks()
		self.assertEqual(
			set(webhook),
			{"name", "url", "enabled", "events", "auto_disabled_at", "is_failing", "last_sent_at"},
		)
		self.assertEqual(webhook["events"], ["menu_updated", "page_updated"])
		self.assertEqual((webhook["enabled"], webhook["is_failing"]), (True, True))
		self.assertIsNotNone(webhook["last_sent_at"])

		details = webhooks_api.get_webhook(created["name"])
		self.assertEqual(
			(
				details["failed_attempts"],
				details["failure_limit"],
				details["failing_count"],
				details["last_error"],
			),
			(1, FAILURE_LIMIT, 1, "503 Service Unavailable"),
		)
		self.assertEqual(details["secret_hint"], created["secret"][-4:])

		logs = webhooks_api.get_webhook_logs(created["name"])
		self.assertEqual(logs["total"], 1)
		log = webhooks_api.get_webhook_log(logs["rows"][0]["name"])
		self.assertEqual(log["is_test"], False)
		self.assertEqual(
			[header for header, _value in log["headers"]], [EVENT_HEADER, EVENT_ID_HEADER, SIGNATURE_HEADER]
		)

	def test_a_commera_admin_manages_webhooks_and_a_commera_user_cannot(self):
		add_commera_roles()
		create_user(WEBHOOK_ADMIN, COMMERA_ADMIN)
		create_user(WEBHOOK_PICKER, COMMERA_USER)

		with self.set_user(WEBHOOK_ADMIN):
			created = webhooks_api.create_webhook("https://store.example.com/hook", ["menu_updated"])
			self.assertEqual([webhook["name"] for webhook in webhooks_api.get_webhooks()], [created["name"]])
		with self.set_user(WEBHOOK_PICKER), self.assertRaises(frappe.PermissionError):
			webhooks_api.get_webhooks()

	def test_a_webhook_needs_an_event_and_a_web_url(self):
		with self.assertRaisesRegex(frappe.ValidationError, "at least one event"):
			make_webhook([])
		with self.assertRaisesRegex(frappe.ValidationError, "must start with"):
			make_webhook(["menu_updated"], url="ftp://store.example.com")

	def test_a_webhook_cannot_point_at_the_server_or_its_network(self):
		for url in (
			"http://store.example.com/hook",
			"https://127.0.0.1/hook",
			"https://169.254.169.254/latest",
		):
			with self.subTest(url=url), self.assertRaises(frappe.ValidationError):
				make_webhook(["menu_updated"], url=url)
		with patch("commera.webhooks.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.5", 0))]):
			with self.assertRaisesRegex(frappe.ValidationError, "public address"):
				make_webhook(["menu_updated"], url="https://internal.example.com/hook")

	def test_the_site_config_allows_local_urls_for_development(self):
		with patch.dict(frappe.conf, {ALLOW_LOCAL_URLS_CONFIG: 1}):
			webhook = make_webhook(["menu_updated"], url="http://127.0.0.1:3100/api/webhooks/commera")
		self.assertEqual(webhook.url, "http://127.0.0.1:3100/api/webhooks/commera")

	def test_a_name_that_now_points_inside_is_not_posted_to(self):
		webhook = make_webhook(["menu_updated"])
		with (
			patch("commera.webhooks.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 0))]),
			patch("commera.webhooks.requests.post") as post,
		):
			self.deliver_and_fail(self.make_event("menu_updated", {}), post=post)

		post.assert_not_called()
		[log] = get_logs(webhook.name)
		self.assertIn("public address", log.error)

	def test_a_redirect_is_a_failure_and_is_not_followed(self):
		webhook = make_webhook(["menu_updated"])
		self.deliver_and_fail(
			self.make_event("menu_updated", {}), post=lambda url, **kwargs: make_response(302, "Found")
		)

		[log] = get_logs(webhook.name)
		self.assertEqual((log.status, log.error), ("Retrying", "302 Found"))

	def test_deleting_a_webhook_deletes_its_logs(self):
		webhook = make_webhook(["menu_updated"])
		with patch("commera.webhooks.requests.post", return_value=make_response()):
			deliver(self.make_event("menu_updated", {}))

		webhooks_api.delete_webhook(webhook.name)

		self.assertFalse(frappe.db.exists(LOG_DOCTYPE, {"webhook": webhook.name}))

	def test_storefront_changes_wait_for_a_subscriber_and_batch_per_transaction(self):
		frappe.local.flags.pop(plugin_events.CHANGED_STOREFRONT_FLAG, None)
		self.addCleanup(frappe.local.flags.pop, plugin_events.CHANGED_STOREFRONT_FLAG, None)
		plugin_events.add_storefront_change("menu_updated", "Commera Settings", "Commera Settings")
		self.assertIsNone(frappe.local.flags.get(plugin_events.CHANGED_STOREFRONT_FLAG))

		make_webhook(["menu_updated", "collection_updated"])
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
			make_webhook(["page_updated", "page_updated"])


class TestWebhookOrderEvents(IntegrationTestCase):
	def setUp(self):
		reset_webhooks(self)
		frappe.db.after_commit.reset()

	def get_events(self, reference_name: str) -> list[str]:
		return frappe.get_all("Commera Event", filters={"reference_name": reference_name}, pluck="event")

	def test_a_store_order_save_fires_order_updated_only_when_subscribed(self):
		sales_order = make_test_sales_order(order_type=STORE_ORDER_TYPE)
		plugin_events.on_sales_order_update_after_submit(sales_order)
		self.assertNotIn("order_updated", self.get_events(sales_order.name))

		make_webhook(["order_updated"])
		plugin_events.on_sales_order_update_after_submit(sales_order)
		plugin_events.on_sales_order_update_after_submit(sales_order)

		self.assertEqual(self.get_events(sales_order.name).count("order_updated"), 1)

	def test_a_status_change_fires_order_updated_once_per_status(self):
		sales_order = make_test_sales_order(order_type=STORE_ORDER_TYPE)
		make_webhook(["order_updated"])
		frappe.db.set_value(
			"Sales Order", sales_order.name, "custom_ecommerce_status", "Waiting for Approval"
		)

		update_sales_order_ecommerce_status(sales_order.name)
		update_sales_order_ecommerce_status(sales_order.name)

		self.assertEqual(self.get_events(sales_order.name).count("order_updated"), 1)
		data = frappe.parse_json(
			frappe.db.get_value(
				"Commera Event", {"reference_name": sales_order.name, "event": "order_updated"}, "data"
			)
		)
		self.assertEqual(
			data["status"], frappe.db.get_value("Sales Order", sales_order.name, "custom_ecommerce_status")
		)
