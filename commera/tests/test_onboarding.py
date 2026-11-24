from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import frappe
from frappe.tests import IntegrationTestCase
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera import onboarding
from commera.api.admin import onboarding as onboarding_api
from commera.install import SALE_PRICE_LIST, TEST_ABBR, TEST_COMPANY
from commera.migrate import set_default_app
from commera.roles import COMMERA_ADMIN
from commera.www.commera import get_boot

SETTINGS = "Commera Settings"
STORE = {
	"store_name": "Zz Onboarding Store",
	"country": "India",
	"currency": "INR",
	"time_zone": "Asia/Kolkata",
}
OTHER_COMPANY = "Zz Onboarding Other Company"
FOREIGN_PRICE_LIST = "Zz Onboarding USD Selling"


OTHER_WAREHOUSE = "Zz Onboarding Stores - ZZOOC"
BARE_COMPANY = "Zz Onboarding Bare Company"
BARE_CURRENCY = "ISK"
FIXTURE_SAVEPOINT = "existing_store_fixtures"
TEST_SAVEPOINT = "existing_store_test"


def make_other_company():
	frappe.get_doc(
		{
			"doctype": "Company",
			"name": OTHER_COMPANY,
			"company_name": OTHER_COMPANY,
			"abbr": "ZZOOC",
			"default_currency": "USD",
			"country": "United States",
			"chart_of_accounts": "Standard",
		}
	).db_insert()
	frappe.get_doc(
		{
			"doctype": "Warehouse",
			"name": OTHER_WAREHOUSE,
			"warehouse_name": "Zz Onboarding Stores",
			"company": OTHER_COMPANY,
			"is_group": 0,
		}
	).db_insert()
	frappe.get_doc(
		{"doctype": "Price List", "price_list_name": FOREIGN_PRICE_LIST, "selling": 1, "currency": "USD"}
	).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Company",
			"name": BARE_COMPANY,
			"company_name": BARE_COMPANY,
			"abbr": "ZZOBC",
			"default_currency": BARE_CURRENCY,
			"country": "Iceland",
			"chart_of_accounts": "Standard",
		}
	).db_insert()


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

	def test_running_while_the_job_waits_for_the_request_to_commit_is_still_running(self):
		with patch("frappe.enqueue"):
			onboarding.queue_store_setup({"company_name": STORE["store_name"]})
		self.addCleanup(frappe.cache.delete_value, onboarding.SETUP_QUEUEING_CACHE_KEY)

		with patch("commera.onboarding.is_job_enqueued", return_value=False):
			self.assertEqual(onboarding.get_setup_status(), {"status": "running", "error": None})
			frappe.cache.delete_value(onboarding.SETUP_QUEUEING_CACHE_KEY)
			self.assertEqual(onboarding.get_setup_status()["status"], "failed")

	@patch("frappe.enqueue")
	@patch("frappe.is_setup_complete", return_value=False)
	def test_rejects_invalid_store_details(self, _setup_complete, _enqueue):
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
			lambda: onboarding_api.save_brand(brand_logo=""),
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

	def open_desk(self, user, path):
		self.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
		frappe.local.request = Request(EnvironBuilder(path=path).get_environ())
		frappe.flags.redirect_location = None
		frappe.set_user(user)
		with patch.object(onboarding.frappe, "is_setup_complete", return_value=False):
			try:
				onboarding.redirect_from_desk_before_setup(frappe._dict())
			except frappe.Redirect:
				return frappe.flags.redirect_location

	def test_owner_is_sent_to_onboarding_from_desk_and_the_wizard(self):
		for path in ("/desk", "/desk/setup-wizard", "/desk/user"):
			with self.subTest(path=path):
				self.assertEqual(self.open_desk(self.owner, path), "/commera")

	def test_other_desk_users_see_setup_pending_message(self):
		location = self.open_desk(self.store_admin, "/desk")

		self.assertTrue(location.startswith("/message?"))
		self.assertIn(
			"Ask the store owner to finish setup.", parse_qs(urlsplit(location).query)["message"][0]
		)

	def test_desk_opens_once_onboarding_is_done(self):
		frappe.db.set_single_value(SETTINGS, "onboarding_completed", 1)

		self.assertIsNone(self.open_desk(self.owner, "/desk/setup-wizard"))
		self.assertIsNone(self.open_desk(self.store_admin, "/desk"))

	def test_desk_opens_on_a_site_already_set_up(self):
		frappe.local.request = Request(EnvironBuilder(path="/desk").get_environ())
		self.addCleanup(setattr, frappe.local, "request", None)
		frappe.set_user(self.owner)

		self.assertTrue(frappe.is_setup_complete())
		self.assertIsNone(onboarding.redirect_from_desk_before_setup(frappe._dict()))

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

	def test_save_brand(self):
		frappe.set_user(self.owner)
		self.assertEqual(
			onboarding_api.save_brand(brand_logo="/files/brand.png"), {"brand_logo": "/files/brand.png"}
		)


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


class ExistingStorePicksTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.db.savepoint(FIXTURE_SAVEPOINT)
		make_other_company()

	@classmethod
	def tearDownClass(cls):
		frappe.db.rollback(save_point=FIXTURE_SAVEPOINT)
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint(TEST_SAVEPOINT)
		self.addCleanup(frappe.db.rollback, save_point=TEST_SAVEPOINT)
		fields = (
			"company",
			"default_price_list",
			"sale_price_list",
			"ecommerce_warehouse",
			"store_setup_status",
			"store_name",
		)
		frappe.db.set_single_value(SETTINGS, {field: "" for field in fields})
		frappe.db.set_single_value("Global Defaults", "default_company", TEST_COMPANY)

	def adopted(self):
		return frappe.db.get_value(
			SETTINGS,
			None,
			["company", "default_price_list", "sale_price_list", "ecommerce_warehouse"],
			as_dict=True,
		)

	def test_several_companies_and_no_default_is_refused(self):
		frappe.db.set_single_value("Global Defaults", "default_company", "")
		with patch("frappe.enqueue") as enqueue, self.assertRaises(frappe.MandatoryError):
			onboarding_api.start_store_setup(**STORE)

		enqueue.assert_not_called()
		self.assertFalse(frappe.db.get_single_value(SETTINGS, "company"))

	def test_the_default_company_sells_with_its_defaults(self):
		with patch("frappe.enqueue") as enqueue:
			status = onboarding_api.start_store_setup(**STORE, price_list="Standard Selling")

		self.assertEqual(status["status"], "done")
		self.assertNotIn(onboarding.run_store_setup, [call.args[0] for call in enqueue.call_args_list])
		self.assertEqual(
			self.adopted(),
			{
				"company": TEST_COMPANY,
				"default_price_list": "Standard Selling",
				"sale_price_list": "Zz Onboarding Store Sale",
				"ecommerce_warehouse": onboarding.get_company_warehouse(TEST_COMPANY),
			},
		)
		self.assertEqual(
			frappe.db.get_value("Price List", "Zz Onboarding Store Sale", ["selling", "enabled", "currency"]),
			(1, 1, frappe.db.get_value("Company", TEST_COMPANY, "default_currency")),
		)
		self.assertFalse(frappe.db.exists("Item Price", {"price_list": "Zz Onboarding Store Sale"}))

	def test_several_price_lists_need_a_pick(self):
		self.assertGreater(len(onboarding.get_selling_price_lists("Zz Onboarding Store", "INR")), 1)
		with self.assertRaises(frappe.MandatoryError):
			onboarding_api.start_store_setup(**STORE)

	def test_the_only_price_list_in_the_company_currency_is_used(self):
		self.assertEqual(
			[row.name for row in onboarding.get_selling_price_lists("Zz Onboarding Store", "USD")],
			[FOREIGN_PRICE_LIST],
		)
		onboarding_api.start_store_setup(**STORE, company=OTHER_COMPANY)

		adopted = self.adopted()
		self.assertEqual(
			(adopted.company, adopted.default_price_list, adopted.ecommerce_warehouse),
			(OTHER_COMPANY, FOREIGN_PRICE_LIST, OTHER_WAREHOUSE),
		)

	def test_a_company_with_no_price_list_or_warehouse_gets_its_own(self):
		self.assertFalse(onboarding.get_selling_price_lists(None, BARE_CURRENCY))
		onboarding_api.start_store_setup(**STORE, company=BARE_COMPANY)

		adopted = self.adopted()
		self.assertEqual(
			(adopted.default_price_list, adopted.sale_price_list, adopted.ecommerce_warehouse),
			("Zz Onboarding Store Selling", "Zz Onboarding Store Sale", "commera_store - ZZOBC"),
		)
		self.assertEqual(
			frappe.db.get_value("Price List", "Zz Onboarding Store Selling", "currency"), BARE_CURRENCY
		)
		self.assertEqual(frappe.db.get_value("Warehouse", "commera_store - ZZOBC", "company"), BARE_COMPANY)

	def test_a_second_run_keeps_the_first_picks(self):
		onboarding_api.start_store_setup(**STORE, price_list=SALE_PRICE_LIST)
		first = self.adopted()
		onboarding_api.start_store_setup(**STORE)

		self.assertEqual(self.adopted(), first)
		self.assertEqual(first.default_price_list, SALE_PRICE_LIST)

	def test_price_list_in_another_currency_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			onboarding_api.start_store_setup(**STORE, price_list=FOREIGN_PRICE_LIST)

		self.assertFalse(frappe.db.get_single_value(SETTINGS, "default_price_list"))

	def test_a_saved_warehouse_of_another_company_is_replaced(self):
		frappe.db.set_single_value(SETTINGS, "ecommerce_warehouse", OTHER_WAREHOUSE)
		onboarding_api.start_store_setup(**STORE, price_list="Standard Selling")

		self.assertEqual(self.adopted().ecommerce_warehouse, onboarding.get_company_warehouse(TEST_COMPANY))

	def test_get_onboarding_shows_the_real_company(self):
		frappe.db.set_single_value(SETTINGS, "company", TEST_COMPANY)
		data = onboarding_api.get_onboarding()

		self.assertEqual(data["company_abbr"], TEST_ABBR)
		self.assertEqual(
			data["chart_of_accounts"], frappe.db.get_value("Company", TEST_COMPANY, "chart_of_accounts")
		)
		store = data["existing_store"]
		self.assertEqual(store["company"], TEST_COMPANY)
		self.assertIn(TEST_COMPANY, [company.name for company in store["companies"]])
		self.assertIn("Standard Selling", [price_list.name for price_list in store["price_lists"]])

	def test_the_store_sale_list_is_never_offered_as_its_price_list(self):
		frappe.db.set_single_value(
			SETTINGS, {"store_name": "Zz Onboarding Store", "sale_price_list": SALE_PRICE_LIST}
		)
		price_lists = [row.name for row in onboarding_api.get_onboarding()["existing_store"]["price_lists"]]

		self.assertNotIn(SALE_PRICE_LIST, price_lists)
		self.assertIn("Standard Selling", price_lists)

	def test_a_store_commera_set_up_has_no_existing_store(self):
		frappe.db.set_single_value(SETTINGS, "store_setup_status", "done")

		self.assertIsNone(onboarding_api.get_onboarding()["existing_store"])

	def test_a_time_zone_names_its_country(self):
		self.assertEqual(onboarding.get_country_for_time_zone("Asia/Kolkata"), "India")
		self.assertEqual(onboarding.get_country_for_time_zone("Asia/Calcutta"), "India")
		self.assertEqual(onboarding.get_country_for_time_zone("Europe/London"), "United Kingdom")
		self.assertEqual(onboarding.get_country_for_time_zone("America/Denver"), "United States")
		self.assertIsNone(onboarding.get_country_for_time_zone("UTC"))
		self.assertIsNone(onboarding.get_country_for_time_zone("Mars/Olympus"))
		self.assertIsNone(onboarding.get_country_for_time_zone(None))

	def test_a_new_store_starts_in_the_browser_country(self):
		idle = {"status": "idle", "error": None}
		with (
			patch("frappe.is_setup_complete", return_value=False),
			patch("commera.onboarding.get_setup_status", return_value=idle),
		):
			data = onboarding_api.get_onboarding(time_zone="Europe/London")
			unknown = onboarding_api.get_onboarding(time_zone="Mars/Olympus")

		self.assertEqual(
			(data["country"], data["currency"], data["time_zone"]), ("United Kingdom", "GBP", "Europe/London")
		)
		self.assertEqual(
			data["fiscal_year_start_month"], onboarding.get_fiscal_year_start_month("United Kingdom")
		)
		system_settings = frappe.get_single("System Settings")
		self.assertEqual(
			(unknown["country"], unknown["currency"], unknown["time_zone"]),
			(system_settings.country, system_settings.currency, system_settings.time_zone),
		)

	def test_a_store_already_set_up_keeps_its_country(self):
		data = onboarding_api.get_onboarding(time_zone="Europe/London")
		self.assertEqual(data["country"], frappe.db.get_single_value("System Settings", "country"))

	def test_a_fresh_site_has_no_existing_store(self):
		with patch("frappe.is_setup_complete", return_value=False):
			data = onboarding_api.get_onboarding()

		self.assertIsNone(data["existing_store"])
		self.assertEqual(data["chart_of_accounts"], onboarding.DEFAULT_CHART_OF_ACCOUNTS)
