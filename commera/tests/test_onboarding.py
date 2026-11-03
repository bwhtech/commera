from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera import onboarding
from commera.api.admin import onboarding as onboarding_api
from commera.install import TEST_ABBR, TEST_COMPANY
from commera.migrate import set_default_app
from commera.roles import COMMERA_ADMIN
from commera.www.commera import get_boot

SETTINGS = "Commera Settings"
STORE = {
	"store_name": "Zz Onboarding Store",
	"store_category": "Home",
	"country": "India",
	"currency": "INR",
	"time_zone": "Asia/Kolkata",
}


class OnboardingSetupArgsTestCase(IntegrationTestCase):
	def test_fiscal_year_contains_today(self):
		self.assertEqual(onboarding.get_fiscal_year_dates(4, "2026-11-02"), ("2026-04-01", "2027-03-31"))
		self.assertEqual(onboarding.get_fiscal_year_dates(4, "2026-02-10"), ("2025-04-01", "2026-03-31"))
		self.assertEqual(onboarding.get_fiscal_year_dates(1, "2026-11-02"), ("2026-01-01", "2026-12-31"))
		self.assertEqual(onboarding.get_fiscal_year_dates(3, "2027-03-01"), ("2027-03-01", "2028-02-29"))

	def test_fiscal_year_start_month_follows_country(self):
		self.assertEqual(onboarding.get_fiscal_year_start_month("India"), 4)
		self.assertEqual(onboarding.get_fiscal_year_start_month("Australia"), 7)
		self.assertEqual(onboarding.get_fiscal_year_start_month("Germany"), 1)
		self.assertEqual(onboarding.get_fiscal_year_start_month(None), 1)

	def test_abbr_skips_one_a_company_holds(self):
		self.assertEqual(onboarding.get_company_abbr("Acme goods store"), "AGS")
		self.assertEqual(frappe.db.get_value("Company", TEST_COMPANY, "abbr"), TEST_ABBR)
		self.assertEqual(onboarding.get_company_abbr("Lovely Silk Dresses"), f"{TEST_ABBR}2")

	def test_args_carry_store_but_not_session_user_credentials(self):
		args = onboarding.build_setup_args("Zz Shop", "India", "INR", "Asia/Kolkata")

		self.assertEqual(args["company_name"], "Zz Shop")
		self.assertEqual(args["company_abbr"], "ZS")
		self.assertEqual(args["chart_of_accounts"], "Standard")
		self.assertEqual(args["timezone"], "Asia/Kolkata")
		self.assertTrue(args["fy_start_date"].endswith("-04-01"))
		self.assertTrue(args["fy_end_date"].endswith("-03-31"))
		for key in ("email", "password", "full_name"):
			self.assertNotIn(key, args)

	def test_args_keep_the_site_telemetry_choice(self):
		read_setting = frappe.get_system_settings
		for value in (0, 1):

			def telemetry_is(key, value=value):
				return value if key == "enable_telemetry" else read_setting(key)

			with self.subTest(value=value), patch("frappe.get_system_settings", side_effect=telemetry_is):
				args = onboarding.build_setup_args("Zz Shop", "India", "INR", "Asia/Kolkata")
				self.assertEqual(args["enable_telemetry"], value)

	def test_args_take_explicit_month_and_abbr(self):
		args = onboarding.build_setup_args(
			"Zz Shop", "India", "INR", "Asia/Kolkata", "Standard with Numbers", 1, "ZZQ"
		)

		self.assertEqual(args["company_abbr"], "ZZQ")
		self.assertEqual(args["chart_of_accounts"], "Standard with Numbers")
		self.assertTrue(args["fy_start_date"].endswith("-01-01"))


class StartStoreSetupTestCase(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		onboarding.set_setup_status("")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_setup_already_complete_is_done_without_a_job(self):
		companies = frappe.db.count("Company")
		with patch("frappe.enqueue") as enqueue:
			result = onboarding_api.start_store_setup(**STORE)

		self.assertEqual(result, {"status": "done", "error": None})
		enqueue.assert_not_called()
		self.assertEqual(frappe.db.count("Company"), companies)
		self.assertEqual(frappe.db.get_single_value(SETTINGS, "store_name"), STORE["store_name"])
		self.assertEqual(frappe.db.get_single_value(SETTINGS, "store_category"), STORE["store_category"])

	def test_fresh_site_queues_the_job_once(self):
		with (
			patch("frappe.is_setup_complete", return_value=False),
			patch("commera.onboarding.is_job_enqueued", return_value=True),
			patch("frappe.enqueue") as enqueue,
		):
			first = onboarding_api.start_store_setup(**STORE)
			second = onboarding_api.start_store_setup(**{**STORE, "store_name": "Zz Renamed"})

		self.assertEqual(first, {"status": "running", "error": None})
		self.assertEqual(second, {"status": "running", "error": None})
		enqueue.assert_called_once()
		self.assertEqual(enqueue.call_args.kwargs["job_id"], onboarding.SETUP_JOB_ID)
		self.assertEqual(enqueue.call_args.kwargs["setup_args"]["company_name"], STORE["store_name"])
		# The running job owns the settings, so the second call wrote nothing.
		self.assertEqual(frappe.db.get_single_value(SETTINGS, "store_name"), STORE["store_name"])

	def test_failed_setup_can_be_retried(self):
		onboarding.set_setup_status("failed", "boom")
		with patch("frappe.is_setup_complete", return_value=False), patch("frappe.enqueue") as enqueue:
			self.assertEqual(onboarding_api.get_setup_status(), {"status": "failed", "error": "boom"})
			result = onboarding_api.start_store_setup(**STORE)

		self.assertEqual(result["status"], "running")
		enqueue.assert_called_once()

	def test_running_without_a_job_reports_failed(self):
		onboarding.set_setup_status("running")
		with patch("commera.onboarding.is_job_enqueued", return_value=False):
			status = onboarding.get_setup_status()

		self.assertEqual(status["status"], "failed")
		self.assertTrue(status["error"])

	def test_rejects_invalid_store_details(self):
		for override in (
			{"store_name": "  "},
			{"country": "Atlantis"},
			{"time_zone": "Mars/Base"},
			{"chart_of_accounts": "Nonexistent Chart"},
			{"fiscal_year_start_month": 13},
			{"company_abbr": TEST_ABBR},
		):
			with self.subTest(override=override), self.assertRaises(frappe.ValidationError):
				onboarding_api.start_store_setup(**{**STORE, **override})

	def test_job_failure_is_recorded_with_its_reason(self):
		with (
			patch("commera.onboarding.run_frappe_setup", side_effect=RuntimeError("no company")),
			patch.object(frappe.db, "rollback"),
			patch("frappe.log_error"),
			patch("frappe.publish_realtime") as publish,
		):
			onboarding.run_store_setup({"company_name": "Zz Missing"})

		with patch("frappe.is_setup_complete", return_value=False):
			status = onboarding.get_setup_status()
		self.assertEqual(status["status"], "failed")
		self.assertIn("no company", status["error"])
		self.assertEqual(publish.call_args.args[0], onboarding.SETUP_REALTIME_EVENT)
		self.assertEqual(publish.call_args.args[1]["status"], "failed")


class OnboardingAccessTestCase(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.store_admin = self.make_user("zz-onboarding-admin@example.com", COMMERA_ADMIN)
		self.owner = self.make_user("zz-onboarding-owner@example.com", "System Manager")
		frappe.db.set_single_value(SETTINGS, "onboarding_completed", 0)

	def tearDown(self):
		frappe.set_user("Administrator")

	def make_user(self, email, role):
		if not frappe.db.exists("User", email):
			user = frappe.new_doc("User")
			user.email, user.first_name = email, "Zz"
			user.flags.no_welcome_mail = True
			user.insert(ignore_permissions=True)
			user.add_roles(role)
		return email

	def test_store_admin_without_system_manager_is_refused(self):
		frappe.set_user(self.store_admin)
		calls = (
			onboarding_api.get_onboarding,
			onboarding_api.get_setup_status,
			onboarding_api.complete_onboarding,
			lambda: onboarding_api.save_profile("Zz Name"),
			lambda: onboarding_api.start_store_setup(**STORE),
			lambda: onboarding_api.save_brand(primary_color="#000000"),
			lambda: onboarding_api.save_selling(1, 1),
		)
		for call in calls:
			with self.subTest(call=call), self.assertRaises(frappe.PermissionError):
				call()

	def test_boot_flags_pending_onboarding_for_system_manager_only(self):
		frappe.set_user(self.owner)
		self.assertTrue(get_boot().onboarding_pending)

		frappe.set_user(self.store_admin)
		self.assertFalse(get_boot().onboarding_pending)

		frappe.set_user(self.owner)
		onboarding_api.complete_onboarding()
		self.assertFalse(get_boot().onboarding_pending)

	def test_get_onboarding_prefills_from_system_settings(self):
		frappe.set_user(self.owner)
		data = onboarding_api.get_onboarding()

		self.assertEqual(data["country"], frappe.db.get_single_value("System Settings", "country"))
		self.assertEqual(data["email"], self.owner)
		self.assertIn(data["setup"]["status"], ("idle", "running", "done", "failed"))
		self.assertTrue(1 <= data["fiscal_year_start_month"] <= 12)
		self.assertIn("Standard", data["options"]["charts_of_accounts"])
		self.assertIn("India", data["options"]["countries"])
		self.assertIn("Asia/Kolkata", data["options"]["time_zones"])

	def test_country_defaults_follow_the_picked_country(self):
		frappe.set_user(self.owner)
		defaults = onboarding_api.get_country_defaults("United Kingdom")

		self.assertEqual(defaults["currency"], "GBP")
		self.assertEqual(defaults["time_zone"], "Europe/London")
		self.assertEqual(defaults["fiscal_year_start_month"], 4)
		self.assertIn("Standard", defaults["charts_of_accounts"])

	def test_save_profile_splits_name_and_sets_password(self):
		frappe.set_user(self.owner)
		result = onboarding_api.save_profile("Zz Owner Name", password="Zz-onboarding-Pass-9123!")

		self.assertEqual(result["full_name"], "Zz Owner Name")
		self.assertEqual(
			frappe.db.get_value("User", self.owner, ["first_name", "last_name"]), ("Zz", "Owner Name")
		)
		self.assertTrue(onboarding.has_password(self.owner))

	def test_save_selling_and_brand(self):
		frappe.set_user(self.owner)
		self.assertEqual(
			onboarding_api.save_selling(0, 1), {"cod_enabled": False, "allow_guest_checkout": True}
		)
		self.assertEqual(onboarding_api.save_brand(primary_color="#1d4ed8")["primary_color"], "#1d4ed8")
		with self.assertRaises(frappe.ValidationError):
			onboarding_api.save_brand(primary_color="red; background: url(x)")


class InstallOnSiteInUseTestCase(IntegrationTestCase):
	"""Commera installed on a site whose Frappe setup already ran, next to people using ERPNext."""

	def setUp(self):
		frappe.set_user("Administrator")
		system_default = frappe.db.get_single_value("System Settings", "default_app")
		user_default = frappe.db.get_value("User", "Administrator", "default_app")
		company = frappe.db.get_single_value(SETTINGS, "company")
		self.addCleanup(frappe.db.set_single_value, "System Settings", "default_app", system_default)
		self.addCleanup(frappe.db.set_value, "User", "Administrator", "default_app", user_default)
		self.addCleanup(frappe.db.set_single_value, SETTINGS, "company", company)
		frappe.db.set_single_value("System Settings", "default_app", "")
		frappe.db.set_value("User", "Administrator", "default_app", "")

	def test_fresh_site_lands_everyone_on_commera(self):
		with patch("frappe.is_setup_complete", return_value=False):
			set_default_app()

		self.assertEqual(frappe.db.get_single_value("System Settings", "default_app"), "commera")

	def test_site_in_use_keeps_its_landing_page(self):
		set_default_app()

		self.assertFalse(frappe.db.get_single_value("System Settings", "default_app"))

	def test_a_chosen_default_is_kept(self):
		frappe.db.set_single_value("System Settings", "default_app", "erpnext")
		with patch("frappe.is_setup_complete", return_value=False):
			set_default_app()

		self.assertEqual(frappe.db.get_single_value("System Settings", "default_app"), "erpnext")

	def test_finishing_onboarding_lands_only_the_owner_on_commera(self):
		onboarding_api.complete_onboarding()

		self.assertEqual(frappe.db.get_value("User", "Administrator", "default_app"), "commera")
		self.assertFalse(frappe.db.get_single_value("System Settings", "default_app"))

	def test_owner_keeps_their_own_choice(self):
		frappe.db.set_value("User", "Administrator", "default_app", "erpnext")
		onboarding_api.complete_onboarding()

		self.assertEqual(frappe.db.get_value("User", "Administrator", "default_app"), "erpnext")

	def test_no_owner_default_where_the_site_already_lands_on_commera(self):
		frappe.db.set_single_value("System Settings", "default_app", "commera")
		onboarding_api.complete_onboarding()

		self.assertFalse(frappe.db.get_value("User", "Administrator", "default_app"))

	def test_store_step_adopts_the_default_company(self):
		frappe.db.set_single_value(SETTINGS, "company", "")
		with patch("frappe.enqueue") as enqueue:
			result = onboarding_api.start_store_setup(**STORE)

		self.assertEqual(result["status"], "done")
		enqueue.assert_not_called()
		default_company = frappe.db.get_single_value("Global Defaults", "default_company")
		self.assertTrue(default_company)
		self.assertEqual(frappe.db.get_single_value(SETTINGS, "company"), default_company)
		self.assertTrue(frappe.db.get_single_value(SETTINGS, "ecommerce_warehouse"))

	def test_store_step_fills_the_rest_for_a_company_already_chosen(self):
		warehouse = frappe.db.get_single_value(SETTINGS, "ecommerce_warehouse")
		self.addCleanup(frappe.db.set_single_value, SETTINGS, "ecommerce_warehouse", warehouse)
		frappe.db.set_single_value(SETTINGS, {"company": TEST_COMPANY, "ecommerce_warehouse": ""})
		onboarding_api.start_store_setup(**STORE)

		self.assertEqual(frappe.db.get_single_value(SETTINGS, "company"), TEST_COMPANY)
		self.assertEqual(
			frappe.db.get_single_value(SETTINGS, "ecommerce_warehouse"),
			onboarding.get_company_warehouse(TEST_COMPANY),
		)
