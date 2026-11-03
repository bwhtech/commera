import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.data import now_datetime

import commera
from commera import onboarding, setup_state, telemetry
from commera.api.admin import onboarding as onboarding_api
from commera.api.admin import telemetry as telemetry_api
from commera.api.admin.catalog import create_product
from commera.api.admin.docfields import get_editable_docfields
from commera.api.admin.payments import save_payment_integration
from commera.api.admin.theme import save_theme_settings
from commera.plugin_events import PLUGINS_USER
from commera.telemetry import configuration, milestones, scan
from commera.telemetry import onboarding as onboarding_telemetry

CAPTURE = "commera.telemetry.frappe_telemetry.capture"
PULSE_ENABLED = "commera.telemetry.is_pulse_enabled"
SETTINGS = "Commera Settings"
STORE_NAME = "Zz Telemetry Secret Store"
RAZORPAY_CREDENTIALS = {"key_id": "rzp_test_zz", "key_secret": "zz-key-secret", "webhook_secret": "zz-hook"}
STORE = {
	"store_name": STORE_NAME,
	"store_category": "Home",
	"country": "India",
	"currency": "INR",
	"time_zone": "Asia/Kolkata",
}
SITE_PROFILE_KEYS = {
	"site_age_days",
	"commera_installed_days_ago",
	"first_product_days_ago",
	"first_gateway_days_ago",
	"first_order_days_ago",
	"first_paid_order_days_ago",
	"last_order_days_ago",
	"products",
	"products_published",
	"variants",
	"collections",
	"gateway_razorpay",
	"gateway_stripe",
	"gateway_telr",
	"gateway_tabby",
	"cod_enabled",
	"shipping_rules",
	"shipping_carriers_enabled",
	"pickup_locations",
	"theme",
	"storefront_pages",
	"plugins_enabled",
	"analytics_integrations",
	"discounts_active",
	"reviews_30d",
	"wishlist_items",
	"oos_subscriptions",
	"guest_checkout_enabled",
	"sessions_30d",
	"product_view_sessions_30d",
	"add_to_cart_sessions_30d",
	"checkout_sessions_30d",
	"gateway_checkouts_30d",
	"gateway_orders_paid_30d",
	"orders_cod_30d",
	"orders_prepaid_30d",
	"orders_7d",
	"orders_30d",
	"orders_cancelled_30d",
	"guest_order_share_bucket",
	"gmv_30d_bucket",
	"aov_bucket",
	"staff_users",
	"staff_active_30d",
	"customers",
}
PROPERTY_LIMIT_BYTES = 4096


def insert_raw(doctype: str, **fields):
	"""A bare row, without the controller: the facts read rows, not documents."""
	doc = frappe.get_doc({"doctype": doctype, "name": frappe.generate_hash(length=10), **fields})
	doc.db_insert()
	return doc


class TelemetryTestCase(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.clear_document_cache, SETTINGS, SETTINGS)
		self.addCleanup(frappe.set_user, "Administrator")
		self.capture = self.start_patch(patch(CAPTURE))
		self.pulse_enabled = self.start_patch(patch(PULSE_ENABLED, return_value=True))

	def start_patch(self, patcher):
		started = patcher.start()
		self.addCleanup(patcher.stop)
		return started

	def get_events(self, event: str) -> list[dict]:
		return [call.kwargs["properties"] for call in self.capture.call_args_list if call.args[0] == event]

	def get_milestones(self, milestone: str) -> list[dict]:
		return [
			properties
			for properties in self.get_events("store_milestone_reached")
			if properties["milestone"] == milestone
		]

	def make_collection(self) -> str:
		item_group = frappe.new_doc("Item Group")
		item_group.item_group_name = f"Telemetry Group {frappe.generate_hash(length=6)}"
		item_group.parent_item_group = "All Item Groups"
		item_group.custom_displayname = item_group.item_group_name
		return item_group.insert().name

	def add_product(self, collection: str) -> str:
		return create_product(
			title=f"Telemetry Product {frappe.generate_hash(length=6)}", collection=collection
		)["name"]

	def switch_off_payment_methods(self):
		frappe.db.sql("update `tabPayment Gateway Profile` set enabled = 0")
		frappe.db.set_single_value(SETTINGS, "cod_enabled", 0)


class TelemetryCaptureTestCase(TelemetryTestCase):
	def test_default_properties_carry_version_and_hosting(self):
		with patch.dict(frappe.conf, {"fc_team": None}):
			self.assertEqual(
				telemetry.default_properties(), {"app_version": commera.__version__, "hosting": "self_hosted"}
			)
		with patch.dict(frappe.conf, {"fc_team": "zz-team"}):
			self.assertEqual(telemetry.get_hosting(), "frappe_cloud")
			with patch("frappe.get_installed_apps", return_value=["frappe", "commera", "commera_cloud"]):
				self.assertEqual(telemetry.get_hosting(), "commera_cloud")

	def test_boot_config_says_whether_telemetry_is_on(self):
		config = telemetry.get_boot_config()
		self.assertTrue(config["enabled"])
		self.assertIn("site_age", config)
		self.pulse_enabled.return_value = False
		self.assertEqual(telemetry.get_boot_config(), {"enabled": False})

	def test_capture_adds_default_properties(self):
		telemetry.capture("zz_event", interval="1d", step="you")

		self.capture.assert_called_once()
		self.assertEqual(self.capture.call_args.args, ("zz_event", "commera"))
		self.assertEqual(self.capture.call_args.kwargs["interval"], "1d")
		properties = self.capture.call_args.kwargs["properties"]
		self.assertEqual(properties["step"], "you")
		self.assertEqual(properties["app_version"], commera.__version__)

	def test_capture_and_event_functions_swallow_errors(self):
		self.capture.side_effect = RuntimeError("pulse is down")
		telemetry.capture("zz_event")

		@telemetry.telemetry_event
		def broken():
			raise ValueError("bad property")

		self.assertIsNone(broken())

	def test_event_functions_do_nothing_when_telemetry_is_off(self):
		self.pulse_enabled.return_value = False

		@telemetry.telemetry_event
		def tracked():
			raise AssertionError("ran with telemetry off")

		self.assertIsNone(tracked())

	def test_registry_value_and_buckets(self):
		self.assertEqual(telemetry.registry_value("stripe", ("stripe",)), "stripe")
		self.assertEqual(telemetry.registry_value("my_gateway", ("stripe",)), "other")
		self.assertEqual(telemetry.rows_bucket(9), "lt_10")
		self.assertEqual(telemetry.rows_bucket(100), "100_1000")
		self.assertEqual(telemetry.rows_bucket(5000), "gt_1000")
		self.assertEqual(telemetry.value_bucket(150), "100_1k")
		self.assertEqual(telemetry.duration_bucket(45), "30_60s")
		self.assertEqual(telemetry.duration_bucket(500), "gt_120s")
		self.assertEqual(telemetry.error_kind(frappe.MandatoryError("Store name")), "mandatory")
		self.assertEqual(telemetry.error_kind(frappe.ValidationError("Store name")), "validation")
		self.assertEqual(telemetry.error_kind(KeyError("Store name")), "other")
		self.assertEqual(telemetry.theme_value("Summer Theme"), "summer_theme")
		self.assertEqual(telemetry.theme_value("Acme Private Theme"), "custom")

	def test_source_follows_the_flag_then_the_plugin_user(self):
		self.assertEqual(telemetry.get_source(), "person")
		with telemetry.data_source("demo_data"):
			self.assertEqual(telemetry.get_source(), "demo_data")
		self.assertEqual(telemetry.get_source(), "person")
		frappe.set_user(PLUGINS_USER)
		self.assertEqual(telemetry.get_source(), "plugin")


class ProductMilestoneTestCase(TelemetryTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete(setup_state.PRODUCT_DOCTYPE)
		self.collection = self.make_collection()

	def test_first_product_fires_once(self):
		self.add_product(self.collection)
		self.add_product(self.collection)

		reached = self.get_milestones("first_product_created")
		self.assertEqual(len(reached), 1)
		self.assertEqual(reached[0]["source"], "person")
		self.assertIsInstance(reached[0]["days_since_install"], int)

	def test_demo_data_product_is_not_a_person(self):
		with telemetry.data_source("demo_data"):
			self.add_product(self.collection)
		self.add_product(self.collection)

		reached = self.get_milestones("first_product_created")
		self.assertEqual([properties["source"] for properties in reached], ["demo_data"])

	def test_first_published_product_fires_once(self):
		frappe.db.sql("update `tabStyle Attribute Variant` set is_published = 0")
		self.add_product(self.collection)
		self.add_product(self.collection)
		for variant_name in frappe.get_all("Style Attribute Variant", pluck="name", limit=2):
			self.publish(variant_name)

		self.assertEqual(len(self.get_milestones("first_product_published")), 1)

	def publish(self, variant_name: str):
		"""The controller refuses a variant with no photos, so the row is published and the hook run on it."""
		variant = frappe.get_doc("Style Attribute Variant", variant_name)
		variant._doc_before_save = frappe.copy_doc(variant)
		variant.db_set("is_published", 1)
		milestones.on_variant_update(variant)

	def test_setup_state_reads_the_same_facts(self):
		state = onboarding_api.get_setup_state()
		self.assertFalse(state["product"])
		self.assertEqual(set(state), {"product", "payments", "shipping", "theme"})

		self.add_product(self.collection)
		self.assertTrue(onboarding_api.get_setup_state()["product"])


class PaymentMilestoneTestCase(TelemetryTestCase):
	def setUp(self):
		super().setUp()
		self.switch_off_payment_methods()
		frappe.clear_document_cache("Razorpay Gateway Settings", "Razorpay Gateway Settings")

	def test_gateway_enabled_only_on_off_to_on(self):
		save_payment_integration("razorpay", 1, RAZORPAY_CREDENTIALS)
		save_payment_integration("razorpay", 1, RAZORPAY_CREDENTIALS)

		enabled = self.get_events("payment_gateway_enabled")
		self.assertEqual(len(enabled), 1)
		self.assertEqual(enabled[0]["gateway"], "razorpay")
		self.assertIn("live_mode", enabled[0])
		reached = self.get_milestones("payment_method_enabled")
		self.assertEqual([properties["payment_method"] for properties in reached], ["razorpay"])
		self.assertTrue(onboarding_api.get_setup_state()["payments"])

	def test_gateway_disabled_after_enabled(self):
		save_payment_integration("razorpay", 1, RAZORPAY_CREDENTIALS)
		frappe.db.set_single_value(SETTINGS, "cod_enabled", 1)
		save_payment_integration("razorpay", 0)

		disabled = self.get_events("payment_gateway_disabled")
		self.assertEqual(len(disabled), 1)
		self.assertEqual(disabled[0]["days_enabled"], 0)

	def test_gateway_save_failed_reports_missing_fields(self):
		frappe.db.set_single_value("Razorpay Gateway Settings", "key_id", None)
		with self.assertRaises(frappe.MandatoryError):
			save_payment_integration("razorpay", 1, {"key_id": ""})

		self.assertEqual(
			self.get_events("payment_gateway_save_failed")[0],
			self.with_defaults("razorpay", "missing_fields"),
		)

	def with_defaults(self, gateway: str, reason: str) -> dict:
		return {**telemetry.default_properties(), "gateway": gateway, "reason": reason}

	def test_cod_switched_on_in_settings(self):
		settings = frappe.get_doc(SETTINGS)
		settings.cod_enabled = 1
		settings.save()

		self.assertEqual(self.get_events("cod_toggled")[0]["enabled"], True)
		reached = self.get_milestones("payment_method_enabled")
		self.assertEqual([properties["payment_method"] for properties in reached], ["cod"])


class ShippingAndThemeMilestoneTestCase(TelemetryTestCase):
	def test_shipping_configured_fires_once(self):
		frappe.db.delete("Shipping Rule", setup_state.STORE_SHIPPING_RULES)
		frappe.db.sql("update `tabShipping Provider Profile` set enabled = 0")
		for label in ("Zz One", "Zz Two"):
			rule = insert_raw("Shipping Rule", label=label, shipping_rule_type="Selling")
			milestones.on_shipping_rule_insert(rule)

		self.assertEqual(len(self.get_milestones("shipping_configured")), 1)

	def test_theme_customized_fires_once(self):
		self.reset_summer_theme()
		self.assertFalse(setup_state.is_theme_customized())

		save_theme_settings(hero_caption="Zz caption")
		save_theme_settings(hero_caption="Zz another caption")

		self.assertEqual(len(self.get_milestones("theme_customized")), 1)
		self.assertTrue(onboarding_api.get_setup_state()["theme"])

	def reset_summer_theme(self):
		frappe.db.set_single_value("Shop Theme Settings", "active_theme", setup_state.DEFAULT_THEME)
		frappe.db.delete("Theme Layout")
		settings_doctype = frappe.db.get_value("Shop Theme", setup_state.DEFAULT_THEME, "theme_settings")
		for _group_label, docfield in get_editable_docfields(settings_doctype):
			frappe.db.set_single_value(settings_doctype, docfield.fieldname, docfield.default)
		frappe.clear_document_cache(settings_doctype, settings_doctype)
		frappe.clear_document_cache("Shop Theme Settings", "Shop Theme Settings")


class OrderMilestoneTestCase(TelemetryTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("Sales Order", {"order_type": "Shopping Cart"})
		frappe.db.delete("Gateway Payment Request", {"ref_doctype": "Quotation"})

	def add_order(self) -> str:
		order = insert_raw(
			"Sales Order",
			order_type="Shopping Cart",
			docstatus=1,
			per_billed=100,
			custom_ecommerce_payment_mode="COD",
		)
		for event in ("order_placed", "order_paid"):
			milestones.on_commera_event_insert(
				frappe._dict(reference_doctype="Sales Order", reference_name=order.name, event=event)
			)
		return order.name

	def test_first_gateway_checkout_fires_once(self):
		for _attempt in range(2):
			request = insert_raw("Gateway Payment Request", ref_doctype="Quotation", gateway="Razorpay")
			milestones.on_gateway_payment_request_insert(request)

		reached = self.get_milestones("first_gateway_checkout")
		self.assertEqual([properties["payment_method"] for properties in reached], ["razorpay"])

	def test_order_milestones_fire_once(self):
		for _order in range(11):
			self.add_order()

		self.assertEqual(len(self.get_milestones("first_order_placed")), 1)
		paid = self.get_milestones("first_order_paid")
		self.assertEqual(len(paid), 1)
		self.assertEqual(paid[0]["payment_method"], "cod")
		self.assertFalse(paid[0]["is_guest"])
		self.assertEqual(len(self.get_milestones("tenth_order_paid")), 1)


class ConfigurationEventsTestCase(TelemetryTestCase):
	def test_discount_and_page_created(self):
		configuration.on_discount_insert(frappe._dict(discount_type="Buy X Get Y", method="Code"))
		configuration.on_page_insert(frappe._dict())

		discount = self.get_events("discount_created")[0]
		self.assertEqual((discount["type"], discount["has_code"]), ("buy_x_get_y", True))
		self.assertEqual(len(self.get_events("storefront_page_created")), 1)

	def test_shipping_rule_saved_counts_bands(self):
		rule = frappe._dict(conditions=[frappe._dict(free_shipping=0), frappe._dict(free_shipping=1)])
		configuration.shipping_rule_saved(rule)

		saved = self.get_events("shipping_rule_saved")[0]
		self.assertEqual((saved["bands"], saved["has_free_shipping"]), (2, True))

	def test_analytics_integration_enabled_only_for_new_providers(self):
		settings = frappe._dict(enable_ga4=1, enable_facebook=1, custom_tracking_scripts=[])
		configuration.analytics_saved({"ga4"}, settings)

		self.assertEqual(
			[event["provider"] for event in self.get_events("analytics_integration_enabled")], ["meta"]
		)

	def test_theme_applied_sends_custom_for_a_theme_outside_the_registry(self):
		configuration.theme_activated("Summer Theme", "Summer Theme")
		configuration.theme_activated("Summer Theme", "Zz Private Theme")

		self.assertEqual([event["theme"] for event in self.get_events("theme_applied")], ["custom"])

	def test_plugin_installed_only_for_a_storefront_app(self):
		configuration.on_app_install("commera")
		self.assertEqual(self.get_events("plugin_installed"), [])

		with patch("frappe.get_hooks", return_value=["zz.css"]):
			configuration.on_app_install("zz_private_plugin")
		self.assertEqual(self.get_events("plugin_installed")[0]["plugin"], "other")

	def test_products_imported_outcome(self):
		configuration.products_imported(rows=250, created=3, errors=1)
		configuration.products_imported(rows=4, created=0, errors=4)

		imported = self.get_events("products_imported")
		self.assertEqual([event["rows_bucket"] for event in imported], ["100_1000", "lt_10"])
		self.assertEqual([event["outcome"] for event in imported], ["partial", "failed"])


class OnboardingEventsTestCase(TelemetryTestCase):
	def start_failed_setup(self, **overrides):
		failed = {"status": "failed", "error": "Store setup failed"}
		with patch.object(onboarding, "get_setup_status", return_value=failed), patch("frappe.enqueue"):
			onboarding_api.start_store_setup(**STORE, **overrides)
		return self.get_events("store_setup_started")[-1]

	def test_store_setup_started_with_defaults(self):
		started = self.start_failed_setup()

		self.assertEqual(started["country"], "IN")
		self.assertEqual(started["currency"], "INR")
		self.assertEqual(started["chart_of_accounts"], "standard")
		self.assertFalse(started["chart_overridden"])
		self.assertFalse(started["fiscal_month_overridden"])
		self.assertFalse(started["abbr_overridden"])
		self.assertTrue(started["is_retry"])

	def test_store_setup_started_with_overrides(self):
		started = self.start_failed_setup(
			chart_of_accounts="Standard with Numbers", fiscal_year_start_month=1, company_abbr="ZZQ"
		)

		self.assertEqual(started["chart_of_accounts"], "standard_with_numbers")
		self.assertTrue(started["chart_overridden"])
		self.assertTrue(started["fiscal_month_overridden"])
		self.assertTrue(started["abbr_overridden"])

	def test_store_setup_started_is_not_sent_when_already_done(self):
		with patch("frappe.enqueue"):
			onboarding_api.start_store_setup(**STORE)

		self.assertEqual(self.get_events("store_setup_started"), [])

	def test_store_setup_finished_done(self):
		with (
			patch.object(onboarding, "run_frappe_setup"),
			patch.object(onboarding, "seed_commera_settings"),
			patch.object(onboarding, "create_payment_modes"),
		):
			onboarding.run_store_setup({"company_name": STORE_NAME}, queued_at=now_datetime())

		finished = self.get_events("store_setup_finished")[0]
		self.assertEqual(finished["outcome"], "done")
		self.assertEqual(finished["duration_bucket"], "lt_30s")
		self.assertNotIn("error_kind", finished)

	def test_store_setup_finished_failed_sends_the_kind_not_the_message(self):
		error = frappe.ValidationError(f"{STORE_NAME} could not be made")
		with patch.object(onboarding, "run_frappe_setup", side_effect=error):
			onboarding.run_store_setup({"company_name": STORE_NAME}, queued_at=now_datetime())

		finished = self.get_events("store_setup_finished")[0]
		self.assertEqual(finished["outcome"], "failed")
		self.assertEqual(finished["error_kind"], "validation")
		self.assertNotIn(STORE_NAME, json.dumps(finished))

	def test_onboarding_completed_properties(self):
		frappe.db.set_single_value(
			SETTINGS,
			{
				"store_category": "Home",
				"primary_color": "#123456",
				"cod_enabled": 1,
				"allow_guest_checkout": 0,
			},
		)
		onboarding_api.complete_onboarding()

		completed = self.get_events("onboarding_completed")[0]
		self.assertEqual(completed["store_category"], "home")
		self.assertTrue(completed["custom_colour"])
		self.assertTrue(completed["cod_enabled"])
		self.assertFalse(completed["guest_checkout_enabled"])
		self.assertIn(completed["minutes_since_install"], ("lt_5", "5_15", "15_60", "gt_60"))
		self.assertIsInstance(completed["has_logo"], bool)

	def test_onboarding_completed_sends_other_for_an_unknown_category(self):
		frappe.db.set_single_value(SETTINGS, "store_category", "Zz Private Category")
		onboarding_telemetry.onboarding_completed()

		self.assertEqual(self.get_events("onboarding_completed")[0]["store_category"], "other")


class DashboardEventsTestCase(TelemetryTestCase):
	def test_known_event_goes_out_with_only_known_values(self):
		telemetry_api.record_event(
			"completed_setup_step",
			{
				"step": "store",
				"step_number": "2",
				"total_steps": 7,
				"duration_seconds": 41,
				"store_name": STORE_NAME,
			},
		)

		completed = self.get_events("completed_setup_step")[0]
		self.assertEqual(
			{key: completed[key] for key in ("step", "step_number", "total_steps", "duration_seconds")},
			{"step": "store", "step_number": 2, "total_steps": 7, "duration_seconds": 41},
		)
		self.assertEqual(completed["app_version"], commera.__version__)
		self.assertNotIn("store_name", completed)
		self.assertNotIn(STORE_NAME, json.dumps(completed))
		self.assertEqual(self.capture.call_args.args[1], "commera")

	def test_values_outside_the_list_are_dropped(self):
		telemetry_api.record_event(
			"went_back_in_setup", json.dumps({"from_step": "brand", "to_step": STORE_NAME})
		)
		telemetry_api.record_event("billing_opened", {"surface": "zz-elsewhere", "trial": 1})
		telemetry_api.record_event("products_import_opened", {"surface": "search"})

		self.assertEqual(self.get_events("went_back_in_setup")[0].get("from_step"), "brand")
		self.assertNotIn("to_step", self.get_events("went_back_in_setup")[0])
		self.assertNotIn("surface", self.get_events("billing_opened")[0])
		self.assertTrue(self.get_events("billing_opened")[0]["trial"])
		self.assertEqual(self.get_events("products_import_opened")[0]["surface"], "search")

	def test_pageview_sends_a_route_pattern_never_a_url(self):
		telemetry_api.record_event("pageview", {"route": "/products/:id"})
		telemetry_api.record_event("pageview", {"route": "/products?q=Zz Secret"})
		telemetry_api.record_event("pageview", {"route": "https://zz.example.com/commera"})

		self.assertEqual(
			[properties.get("route") for properties in self.get_events("pageview")],
			["/products/:id", None, None],
		)

	def test_unknown_event_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			telemetry_api.record_event("anything_goes", {})
		self.capture.assert_not_called()

	def test_malformed_properties_never_fail_the_request(self):
		telemetry_api.record_event("left_setup", "{not json")
		telemetry_api.record_event("left_setup", "[1, 2]")

	def test_user_without_dashboard_access_is_refused(self):
		email = "zz-telemetry-no-access@example.com"
		if not frappe.db.exists("User", email):
			user = frappe.new_doc("User")
			user.email, user.first_name = email, "Zz"
			user.flags.no_welcome_mail = True
			user.insert(ignore_permissions=True)
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			telemetry_api.record_event("started_setup", {})
		self.capture.assert_not_called()


class SiteProfileTestCase(TelemetryTestCase):
	def test_collect_sends_only_allowed_keys_under_the_cap(self):
		frappe.db.set_single_value(SETTINGS, "store_name", STORE_NAME)
		profile = scan.collect()
		serialized = json.dumps({**telemetry.default_properties(), **profile}, default=str)

		self.assertEqual(set(profile), SITE_PROFILE_KEYS)
		self.assertLess(len(serialized.encode()), PROPERTY_LIMIT_BYTES)
		self.assertNotIn(STORE_NAME, serialized)

	def test_send_site_profile_does_nothing_when_telemetry_is_off(self):
		with patch(f"{scan.__name__}.is_pulse_enabled", return_value=False):
			scan.send_site_profile()

		self.capture.assert_not_called()

	def test_team_profile_is_sent_only_when_it_changes(self):
		frappe.cache.delete_value(scan.IDENTIFY_CACHE_KEY)
		self.addCleanup(frappe.cache.delete_value, scan.IDENTIFY_CACHE_KEY)
		with patch.dict(frappe.conf, {"fc_team": "zz-team"}), patch(f"{scan.__name__}.identify") as identify:
			scan.send_team_profile()
			scan.send_team_profile()

		identify.assert_called_once()
		self.assertEqual(
			set(identify.call_args.args[0]),
			{"store_country", "store_currency", "commera_activated", "catalogue_size_bucket"},
		)
