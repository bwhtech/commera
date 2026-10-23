# Copyright (c) 2026, company@bwhstudios.com and Contributors
# Tests for the first-party analytics beacon, its payload clamps and the event log retention job.

import json

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import add_days, now_datetime

from commera.analytics import events
from commera.api.admin.analytics import get_base_discount_given
from commera.api.analytics import capture
from commera.api.analytics_dashboard import get_traffic_sources
from commera.commera_ecommerce.doctype.storefront_analytics_event.storefront_analytics_event import (
	StorefrontAnalyticsEvent,
)
from commera.tests import get_test_item

IPAD_USER_AGENT = (
	"Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
	"(KHTML, like Gecko) Version/17.5 Safari/605.1.15"
)
ANDROID_USER_AGENT = (
	"Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
	"Chrome/126.0.0.0 Mobile Safari/537.36"
)
DESKTOP_USER_AGENT = (
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
	"Chrome/126.0.0.0 Safari/537.36"
)


class TestRevenueDiscounts(UnitTestCase):
	def test_codes_and_the_discounts_erpnext_gave_on_its_own_both_count(self):
		allocations = [
			{"discount_class": "Product", "amount": 9},
			{"discount_class": "Order", "amount": 10},
		]
		row = frappe._dict(
			conversion_rate=2,
			base_discount_amount=30,
			custom_discount_allocations=json.dumps(allocations),
		)

		# 18 + 20 from codes in the company currency, plus the 10 a Pricing Rule added to the order discount.
		self.assertEqual(get_base_discount_given(row), 48)

	def test_an_order_without_codes_counts_its_additional_discount(self):
		row = frappe._dict(conversion_rate=1, base_discount_amount=12, custom_discount_allocations=None)

		self.assertEqual(get_base_discount_given(row), 12)


class TestGetDevice(UnitTestCase):
	def test_ipad_is_a_tablet(self):
		self.assertEqual(events.get_device(IPAD_USER_AGENT), "Tablet")

	def test_android_mobi_is_a_mobile(self):
		self.assertEqual(events.get_device(ANDROID_USER_AGENT), "Mobile")

	def test_android_tablet_beats_the_mobi_token(self):
		# Android tablets ship "Tablet" alongside "Mobi"; tablet must win.
		self.assertEqual(events.get_device("Mozilla/5.0 (Linux; Android 14; Tablet) Mobi Safari"), "Tablet")

	def test_desktop_is_the_fallback(self):
		self.assertEqual(events.get_device(DESKTOP_USER_AGENT), "Desktop")

	def test_absent_user_agent_is_blank_not_desktop(self):
		# "" is the doctype's own Literal option; "Desktop" would be a lie about a headless client.
		self.assertEqual(events.get_device(""), "")
		self.assertEqual(events.get_device(None), "")


class TestClip(UnitTestCase):
	def test_none_stays_none(self):
		self.assertIsNone(events.clip(None, 64))

	def test_empty_string_becomes_none(self):
		# "" would otherwise be stored as a distinct, meaningless value.
		self.assertIsNone(events.clip("", 64))

	def test_over_long_value_is_truncated(self):
		self.assertEqual(events.clip("x" * 200, 64), "x" * 64)

	def test_short_value_is_untouched(self):
		self.assertEqual(events.clip("abc", 64), "abc")

	def test_non_string_is_stringified_then_clipped(self):
		self.assertEqual(events.clip(1234567890, 4), "1234")


class TestGetItemsSnapshot(UnitTestCase):
	def test_non_list_input_returns_none(self):
		self.assertIsNone(events.get_items_snapshot({"item_code": "A"}))
		self.assertIsNone(events.get_items_snapshot("SKU-1"))
		self.assertIsNone(events.get_items_snapshot(None))

	def test_json_string_of_a_list_is_parsed(self):
		snapshot = json.loads(events.get_items_snapshot('[{"item_code": "A", "qty": "2", "price": "9.5"}]'))
		self.assertEqual(snapshot, [{"item_code": "A", "qty": 2, "price": 9.5}])

	def test_caps_at_max_snapshot_items(self):
		rows = [{"item_code": f"SKU-{index}", "qty": 1, "price": 1} for index in range(150)]
		snapshot = json.loads(events.get_items_snapshot(rows))
		self.assertEqual(len(snapshot), events.MAX_SNAPSHOT_ITEMS)
		self.assertEqual(snapshot[-1]["item_code"], f"SKU-{events.MAX_SNAPSHOT_ITEMS - 1}")

	def test_non_dict_rows_are_dropped(self):
		snapshot = json.loads(events.get_items_snapshot([{"item_code": "A"}, "junk", 7]))
		self.assertEqual(len(snapshot), 1)

	def test_empty_list_returns_none(self):
		self.assertIsNone(events.get_items_snapshot([]))

	def test_item_code_is_clipped_to_the_link_width(self):
		snapshot = json.loads(events.get_items_snapshot([{"item_code": "z" * 300}]))
		self.assertEqual(len(snapshot[0]["item_code"]), 140)


class AnalyticsCaptureTestBase(IntegrationTestCase):
	def setUp(self):
		self.session_id = frappe.generate_hash(length=32)
		self.set_first_party(1)
		# Drop any inherited request so the form_dict branch is under test and get_user_agent sees none.
		self.saved_request = getattr(frappe.local, "request", None)
		if hasattr(frappe.local, "request"):
			delattr(frappe.local, "request")
		self.saved_form_dict = frappe.local.form_dict

	def tearDown(self):
		frappe.local.form_dict = self.saved_form_dict
		if self.saved_request is not None:
			frappe.local.request = self.saved_request
		elif hasattr(frappe.local, "request"):
			delattr(frappe.local, "request")

	def set_first_party(self, enabled):
		frappe.db.set_single_value("Analytics Settings", "enable_first_party", enabled)
		frappe.clear_document_cache("Analytics Settings", "Analytics Settings")

	def post(self, **payload):
		payload.setdefault("session_id", self.session_id)
		frappe.local.form_dict = frappe._dict(payload)
		capture()

	def captured_rows(self, fields=("name",)):
		return frappe.get_all(
			"Storefront Analytics Event",
			filters={"session_id": self.session_id},
			fields=list(fields),
		)

	def only_captured_row(self, fields):
		rows = self.captured_rows(fields)
		self.assertEqual(len(rows), 1)
		return rows[0]


class TestCaptureEventWhitelist(AnalyticsCaptureTestBase):
	def test_each_client_event_is_accepted(self):
		for event in ("page_view", "view_item", "add_to_cart", "begin_checkout"):
			with self.subTest(event=event):
				self.session_id = frappe.generate_hash(length=32)
				self.post(event=event)
				self.assertEqual(self.only_captured_row(["event"])["event"], event)

	def test_purchase_is_rejected_and_writes_no_row(self):
		# purchase is server-authoritative; accepting it from the browser would let anyone forge revenue.
		with self.assertRaises(frappe.ValidationError):
			self.post(event="purchase", value=99999)
		self.assertEqual(self.captured_rows(), [])

	def test_unknown_event_is_rejected_and_writes_no_row(self):
		with self.assertRaises(frappe.ValidationError):
			self.post(event="drop table")
		self.assertEqual(self.captured_rows(), [])

	def test_missing_event_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.post(path="/en")
		self.assertEqual(self.captured_rows(), [])


class TestCaptureClamps(AnalyticsCaptureTestBase):
	def test_over_long_session_id_is_clipped_to_64(self):
		self.session_id = "s" * 200
		self.post(event="page_view")
		rows = frappe.get_all(
			"Storefront Analytics Event",
			filters={"session_id": "s" * 64},
			fields=["session_id"],
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(len(rows[0]["session_id"]), 64)

	def test_unknown_item_code_is_nulled_rather_than_stored(self):
		# item_code is a Link; a bogus value from the browser would break every report join.
		self.post(event="view_item", item_code=f"NO-SUCH-ITEM-{frappe.generate_hash(length=10)}")
		self.assertIsNone(self.only_captured_row(["item_code"])["item_code"])

	def test_existing_item_code_is_kept(self):
		item_code = get_test_item()
		self.post(event="view_item", item_code=item_code)
		self.assertEqual(self.only_captured_row(["item_code"])["item_code"], item_code)

	def test_items_snapshot_is_capped_at_100_rows(self):
		oversized = [{"item_code": f"SKU-{index}", "qty": 1, "price": 5} for index in range(250)]
		self.post(event="begin_checkout", items=json.dumps(oversized))
		snapshot = json.loads(self.only_captured_row(["items_json"])["items_json"])
		self.assertEqual(len(snapshot), events.MAX_SNAPSHOT_ITEMS)

	def test_over_long_free_text_fields_are_clipped(self):
		self.post(
			event="page_view",
			path="/en/" + ("p" * 400),
			referrer="https://ref.test/" + ("r" * 400),
			utm_source="u" * 400,
			currency="c" * 40,
		)
		row = self.only_captured_row(["path", "referrer", "utm_source", "currency"])
		self.assertEqual(len(row["path"]), 255)
		self.assertEqual(len(row["referrer"]), 255)
		self.assertEqual(len(row["utm_source"]), 140)
		self.assertEqual(len(row["currency"]), 8)

	def test_numeric_fields_are_coerced_from_strings(self):
		self.post(event="add_to_cart", qty="3", value="49.5")
		row = self.only_captured_row(["qty", "value"])
		self.assertEqual(row["qty"], 3)
		self.assertEqual(row["value"], 49.5)

	def test_garbage_numeric_fields_degrade_to_zero(self):
		self.post(event="add_to_cart", qty="lots", value="free")
		row = self.only_captured_row(["qty", "value"])
		self.assertEqual(row["qty"], 0)
		self.assertEqual(row["value"], 0)


class TestCaptureDisabled(AnalyticsCaptureTestBase):
	def test_capture_is_a_no_op_when_first_party_is_off(self):
		self.set_first_party(0)
		self.post(event="page_view")
		self.assertEqual(self.captured_rows(), [])

	def test_disabled_capture_does_not_even_validate_the_event(self):
		# The kill switch must short-circuit before the throw, so an in-flight beacon does not 417.
		self.set_first_party(0)
		self.post(event="purchase")
		self.assertEqual(self.captured_rows(), [])


class TestCaptureVisitorAttribution(AnalyticsCaptureTestBase):
	def test_guest_beacon_has_no_visitor_user(self):
		with self.set_user("Guest"):
			self.post(event="page_view")
		self.assertIsNone(self.only_captured_row(["visitor_user"])["visitor_user"])

	def test_logged_in_beacon_records_the_session_user(self):
		self.post(event="page_view")
		self.assertEqual(self.only_captured_row(["visitor_user"])["visitor_user"], "Administrator")

	def test_device_is_blank_without_a_request(self):
		self.post(event="page_view")
		self.assertEqual(self.only_captured_row(["device"])["device"], "")


class TestClearOldLogs(IntegrationTestCase):
	def make_event(self, session_id, age_days):
		event = frappe.get_doc(
			{
				"doctype": "Storefront Analytics Event",
				"event": "page_view",
				"session_id": session_id,
			}
		).insert(ignore_permissions=True)
		if age_days:
			frappe.db.set_value(
				"Storefront Analytics Event",
				event.name,
				"creation",
				add_days(now_datetime(), -age_days),
				update_modified=False,
			)
		return event.name

	def test_rows_past_the_retention_window_are_deleted(self):
		stale = self.make_event(frappe.generate_hash(length=32), age_days=120)
		fresh = self.make_event(frappe.generate_hash(length=32), age_days=1)

		StorefrontAnalyticsEvent.clear_old_logs(days=90)

		self.assertFalse(frappe.db.exists("Storefront Analytics Event", stale))
		self.assertTrue(frappe.db.exists("Storefront Analytics Event", fresh))

	def test_retention_window_is_the_days_argument(self):
		event = self.make_event(frappe.generate_hash(length=32), age_days=45)

		StorefrontAnalyticsEvent.clear_old_logs(days=90)
		self.assertTrue(frappe.db.exists("Storefront Analytics Event", event))

		StorefrontAnalyticsEvent.clear_old_logs(days=30)
		self.assertFalse(frappe.db.exists("Storefront Analytics Event", event))


class TestGetTrafficSources(IntegrationTestCase):
	"""A window far outside the demo seeder's ~60 days keeps this test's rows the only ones in it."""

	WINDOW_FROM = "2024-01-10"
	WINDOW_TO = "2024-01-12"

	def setUp(self):
		self.event_names = []

	def tearDown(self):
		# get_traffic_sources aggregates the whole window, so leftover rows land in the next test's totals.
		frappe.db.delete("Storefront Analytics Event", {"name": ("in", self.event_names)})

	def make_session(self, session_id, source, medium, campaign, revenue=0):
		events_in_session = [("page_view", 0)] + ([("purchase", revenue)] if revenue else [])
		for event, value in events_in_session:
			row = frappe.get_doc(
				{
					"doctype": "Storefront Analytics Event",
					"event": event,
					"session_id": session_id,
					"utm_source": source,
					"utm_medium": medium,
					"utm_campaign": campaign,
					"value": value,
				}
			).insert(ignore_permissions=True)
			self.event_names.append(row.name)
			frappe.db.set_value(
				"Storefront Analytics Event",
				row.name,
				"creation",
				f"{self.WINDOW_FROM} 10:00:00",
				update_modified=False,
			)

	def get_rows(self):
		return {
			(row["source"], row["medium"], row["campaign"]): row
			for row in get_traffic_sources(self.WINDOW_FROM, self.WINDOW_TO)
		}

	def test_two_campaigns_on_one_channel_stay_separate_rows(self):
		self.make_session("test-diwali-1", "instagram", "social", "diwali", revenue=1000)
		self.make_session("test-diwali-2", "instagram", "social", "diwali")
		self.make_session("test-holi-1", "instagram", "social", "holi", revenue=250)

		rows = self.get_rows()

		self.assertEqual(rows[("instagram", "social", "diwali")]["sessions"], 2)
		self.assertEqual(rows[("instagram", "social", "diwali")]["revenue"], 1000)
		self.assertEqual(rows[("instagram", "social", "holi")]["sessions"], 1)
		self.assertEqual(rows[("instagram", "social", "holi")]["revenue"], 250)

	def test_campaignless_traffic_reports_an_empty_campaign(self):
		self.make_session("test-direct-1", None, None, None)
		self.make_session("test-organic-1", "google", "organic", None)

		rows = self.get_rows()

		self.assertEqual(rows[("Direct", "", "")]["sessions"], 1)
		self.assertEqual(rows[("google", "organic", "")]["sessions"], 1)

	def test_campaign_revenue_sums_to_the_channel_total(self):
		self.make_session("test-diwali-1", "instagram", "social", "diwali", revenue=1000)
		self.make_session("test-holi-1", "instagram", "social", "holi", revenue=250)

		instagram_revenue = sum(
			row["revenue"] for key, row in self.get_rows().items() if key[0] == "instagram"
		)

		self.assertEqual(instagram_revenue, 1250)
