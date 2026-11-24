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
	"store_category": "Home",
	"country": "India",
	"currency": "INR",
	"time_zone": "Asia/Kolkata",
}
OTHER_COMPANY = "Zz Onboarding Other Company"
FOREIGN_PRICE_LIST = "Zz Onboarding USD Selling"


OTHER_WAREHOUSE = "Zz Onboarding Stores - ZZOOC"
FIXTURE_SAVEPOINT = "existing_store_fixtures"


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

	def test_save_selling_and_brand(self):
		frappe.set_user(self.owner)
		self.assertEqual(
			onboarding_api.save_selling(0, 1), {"cod_enabled": False, "allow_guest_checkout": True}
		)
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
		fields = (
			"company",
			"default_price_list",
			"sale_price_list",
			"ecommerce_warehouse",
			"store_setup_status",
		)
		before = frappe.db.get_singles_dict(SETTINGS)
		self.addCleanup(frappe.db.set_single_value, SETTINGS, {field: before.get(field) for field in fields})
		frappe.db.set_single_value(SETTINGS, {field: "" for field in fields})

	def picks(self, **overrides):
		return {
			**STORE,
			"company": TEST_COMPANY,
			"price_list": "Standard Selling",
			"sale_price_list": SALE_PRICE_LIST,
			"warehouse": onboarding.get_company_warehouse(TEST_COMPANY),
			**overrides,
		}

	def test_two_companies_and_no_pick_is_refused(self):
		with patch("frappe.enqueue") as enqueue, self.assertRaises(frappe.MandatoryError):
			onboarding_api.start_store_setup(**STORE)

		enqueue.assert_not_called()
		self.assertFalse(frappe.db.get_single_value(SETTINGS, "company"))

	def test_picks_persist(self):
		picks = self.picks()
		with patch("frappe.enqueue") as enqueue:
			self.assertEqual(onboarding_api.start_store_setup(**picks)["status"], "done")

		self.assertNotIn(onboarding.run_store_setup, [call.args[0] for call in enqueue.call_args_list])
		settings = frappe.get_single(SETTINGS)
		self.assertEqual(
			(
				settings.company,
				settings.default_price_list,
				settings.sale_price_list,
				settings.ecommerce_warehouse,
			),
			(TEST_COMPANY, picks["price_list"], picks["sale_price_list"], picks["warehouse"]),
		)

	def test_no_sale_list_sells_at_the_selling_list(self):
		onboarding_api.start_store_setup(**self.picks(sale_price_list=None))

		self.assertEqual(frappe.db.get_single_value(SETTINGS, "sale_price_list"), "Standard Selling")

	def test_price_list_in_another_currency_is_refused(self):
		for field in ("price_list", "sale_price_list"):
			with self.subTest(field=field), self.assertRaises(frappe.ValidationError):
				onboarding_api.start_store_setup(**self.picks(**{field: FOREIGN_PRICE_LIST}))

	def test_another_companys_warehouse_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			onboarding_api.start_store_setup(**self.picks(warehouse=OTHER_WAREHOUSE))

		self.assertNotEqual(frappe.db.get_single_value(SETTINGS, "ecommerce_warehouse"), OTHER_WAREHOUSE)

	def test_duplicate_creates_an_empty_sale_list(self):
		name = onboarding_api.create_sale_price_list("Zz Onboarding Store", TEST_COMPANY)
		self.addCleanup(frappe.delete_doc, "Price List", name, force=True)

		self.assertEqual(name, "Zz Onboarding Store Sale")
		self.assertEqual(
			frappe.db.get_value("Price List", name, ["selling", "enabled", "currency"], as_dict=True),
			{
				"selling": 1,
				"enabled": 1,
				"currency": frappe.db.get_value("Company", TEST_COMPANY, "default_currency"),
			},
		)
		self.assertFalse(frappe.db.exists("Item Price", {"price_list": name}))
		with self.assertRaises(frappe.DuplicateEntryError):
			onboarding_api.create_sale_price_list("Zz Onboarding Store", TEST_COMPANY)

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
		warehouse_types = frappe.get_all(
			"Warehouse",
			filters={"name": ["in", [row.name for row in store["warehouses"]]]},
			pluck="warehouse_type",
		)
		self.assertNotIn("Transit", warehouse_types)
		self.assertIsInstance(store["importable_count"], int)

	def test_a_store_commera_set_up_has_no_existing_store(self):
		frappe.db.set_single_value(SETTINGS, "store_setup_status", "done")

		self.assertIsNone(onboarding_api.get_onboarding()["existing_store"])

	def test_a_fresh_site_has_no_existing_store(self):
		with patch("frappe.is_setup_complete", return_value=False):
			data = onboarding_api.get_onboarding()

		self.assertIsNone(data["existing_store"])
		self.assertEqual(data["chart_of_accounts"], onboarding.DEFAULT_CHART_OF_ACCOUNTS)
