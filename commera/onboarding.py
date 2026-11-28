from urllib.parse import urlencode

import frappe
from babel.core import get_global
from frappe import _
from frappe.apps import DESK_APP_PATTERN
from frappe.core.doctype.installed_applications.installed_applications import (
	get_setup_wizard_completed_apps,
)
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete, update_global_settings
from frappe.utils.background_jobs import is_job_enqueued
from frappe.utils.data import add_days, add_years, get_abbr, getdate

from commera.core import latest_committed_reads
from commera.migrate import create_payment_modes
from commera.store_options import add_store_options

SETTINGS_DOCTYPE = "Commera Settings"
DEFAULT_PRICE_LIST = "Standard Selling"
DEFAULT_CHART_OF_ACCOUNTS = "Standard"
SETUP_REALTIME_EVENT = "commera_store_setup"
SETUP_QUEUEING_CACHE_KEY = "commera_store_setup_queueing"
SETUP_STAGE_CACHE_KEY = "commera_store_setup_stage"
SETUP_QUEUEING_SECONDS = 30
SETUP_JOB_ID = "commera_store_setup"
SETUP_JOB_TIMEOUT = 1500
MAX_ABBR_LENGTH = 5
STORE_WAREHOUSE_NAME = "commera_store"

# Start months from ERPNext's wizard map (erpnext/public/js/setup_wizard.js), which has no Python copy.
FISCAL_YEAR_START_MONTHS = {
	"Afghanistan": 12,
	"Australia": 7,
	"Bangladesh": 7,
	"Costa Rica": 10,
	"Egypt": 7,
	"Ethiopia": 7,
	"Hong Kong": 4,
	"India": 4,
	"Iran": 6,
	"Kenya": 7,
	"Malaysia": 7,
	"Myanmar": 4,
	"Nepal": 7,
	"New Zealand": 4,
	"Pakistan": 7,
	"Singapore": 4,
	"South Africa": 3,
	"United Kingdom": 4,
}


def is_onboarding_pending(user: str | None = None) -> bool:
	"""Only a System Manager can run setup, so only they are sent to onboarding."""
	if frappe.db.get_single_value(SETTINGS_DOCTYPE, "onboarding_completed"):
		return False
	return "System Manager" in frappe.get_roles(user)


def redirect_from_desk_before_setup(context):
	request = getattr(frappe.local, "request", None)
	if not request or not DESK_APP_PATTERN.match(request.path) or frappe.is_setup_complete():
		return
	if frappe.db.get_single_value(SETTINGS_DOCTYPE, "onboarding_completed"):
		return
	frappe.redirect("/commera" if "System Manager" in frappe.get_roles() else get_setup_pending_message_url())


def get_setup_pending_message_url() -> str:
	query = urlencode(
		{
			"title": _("Store setup in progress"),
			"message": _("This store is still being set up. Ask the store owner to finish setup."),
		}
	)
	return f"/message?{query}"


def get_fiscal_year_start_month(country: str | None) -> int:
	return FISCAL_YEAR_START_MONTHS.get(country, 1)


def get_canonical_time_zone(time_zone: str | None) -> str | None:
	return get_global("zone_aliases").get(time_zone, time_zone)


def get_country_for_time_zone(time_zone: str | None) -> str | None:
	territory = get_global("zone_territories").get(get_canonical_time_zone(time_zone))
	if not territory or territory == "001":
		return None
	return frappe.db.get_value("Country", {"code": territory.lower()})


def get_fiscal_year_dates(start_month: int, today=None) -> tuple[str, str]:
	"""The fiscal year that contains today, starting on the first of `start_month`."""
	today = getdate(today)
	start = today.replace(month=start_month, day=1)
	if start > today:
		start = start.replace(year=start.year - 1)
	end = add_days(add_years(start, 1), -1)
	return start.isoformat(), getdate(end).isoformat()


def get_company_abbr(company_name: str) -> str:
	"""Initials of the name, numbered until no Company holds them: Company.abbr must be unique."""
	base = get_abbr(company_name, MAX_ABBR_LENGTH).upper()
	abbr, suffix = base, 1
	while frappe.db.exists("Company", {"abbr": abbr}):
		suffix += 1
		abbr = f"{base}{suffix}"
	return abbr


def get_language_name() -> str:
	code = frappe.db.get_single_value("System Settings", "language")
	return frappe.db.get_value("Language", code, "language_name") or "English"


def build_setup_args(
	store_name: str,
	country: str,
	currency: str,
	time_zone: str,
	chart_of_accounts: str = DEFAULT_CHART_OF_ACCOUNTS,
	fiscal_year_start_month: int | None = None,
	company_abbr: str | None = None,
) -> dict:
	"""What the desk wizard would send, minus email and password: those would rewrite the session user."""
	start_month = fiscal_year_start_month or get_fiscal_year_start_month(country)
	fy_start_date, fy_end_date = get_fiscal_year_dates(start_month)
	language = get_language_name()
	return {
		# The wizard reads `lang` when the language is not English.
		"language": language,
		"lang": language,
		"country": country,
		"timezone": time_zone,
		"currency": currency,
		"company_name": store_name,
		"company_abbr": company_abbr or get_company_abbr(store_name),
		"chart_of_accounts": chart_of_accounts or DEFAULT_CHART_OF_ACCOUNTS,
		"fy_start_date": fy_start_date,
		"fy_end_date": fy_end_date,
		# The wizard writes this back to System Settings when it finishes; left out, it reads as 0
		# and turns telemetry off on every new store.
		"enable_telemetry": frappe.get_system_settings("enable_telemetry"),
	}


def run_frappe_setup(setup_args: dict):
	"""Run Frappe and ERPNext setup with `setup_args` and fail loudly unless the company now exists."""
	# Once frappe's own stage counts as done (an earlier, failed run marks it), setup_complete skips it and
	# later stages read country/currency off System Settings: run it here so they find this store's region.
	if "frappe" in get_setup_wizard_completed_apps():
		update_global_settings(frappe._dict(setup_args))
	setup_complete(setup_args)

	if not frappe.db.exists("Company", setup_args["company_name"]):
		raise RuntimeError(f"Setup did not create company {setup_args['company_name']}")


def seed_commera_settings(
	company: str,
	price_list: str | None = None,
	sale_price_list: str | None = None,
	warehouse: str | None = None,
):
	"""Fill the mandatory Commera Settings fields, which any later save() would otherwise trip on."""
	# FOR UPDATE: a plain read returns this job's stale snapshot, which save() refuses once the owner
	# has saved brand or selling meanwhile; a locking read sees the latest commit.
	settings = frappe.get_doc(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE, for_update=True)
	settings.company = company
	settings.default_price_list = price_list or settings.default_price_list or DEFAULT_PRICE_LIST
	settings.sale_price_list = sale_price_list or settings.sale_price_list
	settings.ecommerce_warehouse = warehouse or settings.ecommerce_warehouse or get_company_warehouse(company)
	settings.save(ignore_permissions=True)


def adopt_existing_company(store_name: str, company: str | None = None, price_list: str | None = None):
	saved = frappe.db.get_singles_dict(SETTINGS_DOCTYPE, cast=True)
	company = company or get_default_company()
	if not company:
		frappe.throw(_("Pick the company your store sells for"), frappe.MandatoryError)
	currency = frappe.db.get_value("Company", company, "default_currency")
	if not currency:
		frappe.throw(_("Unknown company {0}").format(company))

	price_lists = get_selling_price_lists(store_name, currency, saved.sale_price_list)
	if price_list and price_list not in [row.name for row in price_lists]:
		frappe.throw(_("{0} is not an enabled selling price list in {1}").format(price_list, currency))
	price_list = get_store_price_list(
		store_name, currency, price_lists, price_list or saved.default_price_list
	)
	sale_price_list = saved.sale_price_list
	if not sale_price_list or not frappe.db.exists(
		"Price List", {"name": sale_price_list, "selling": 1, "enabled": 1, "currency": currency}
	):
		sale_price_list = get_or_create_selling_price_list(f"{store_name} Sale", currency)
	warehouse = saved.ecommerce_warehouse
	if not warehouse or frappe.db.get_value("Warehouse", warehouse, "company") != company:
		warehouse = get_company_warehouse(company) or create_store_warehouse(company)
	seed_commera_settings(company, price_list, sale_price_list, warehouse)
	add_store_options()


def get_default_company() -> str | None:
	return (
		frappe.db.get_single_value(SETTINGS_DOCTYPE, "company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or get_only_company()
	)


def get_only_company() -> str | None:
	companies = frappe.get_all("Company", pluck="name", limit=2)
	return companies[0] if len(companies) == 1 else None


def get_selling_price_lists(
	store_name: str | None, currency: str | None = None, sale_price_list: str | None = None
) -> list[dict]:
	filters = {"selling": 1, "enabled": 1}
	if currency:
		filters["currency"] = currency
	sale_lists = [name for name in (sale_price_list, store_name and f"{store_name} Sale") if name]
	if sale_lists:
		filters["name"] = ["not in", sale_lists]
	return frappe.get_all("Price List", filters=filters, fields=["name", "currency"], order_by="name")


def get_store_price_list(store_name: str, currency: str, price_lists: list[dict], picked: str | None) -> str:
	names = [row.name for row in price_lists]
	if picked in names:
		return picked
	if len(names) == 1:
		return names[0]
	if names:
		frappe.throw(_("Pick the price list your store sells at"), frappe.MandatoryError)
	return get_or_create_selling_price_list(f"{store_name} Selling", currency)


def get_or_create_selling_price_list(name: str, currency: str) -> str:
	existing = frappe.db.get_value("Price List", name, ["selling", "enabled", "currency"], as_dict=True)
	if existing and (existing.selling, existing.enabled, existing.currency) == (1, 1, currency):
		return name
	if existing:
		frappe.throw(
			_("Price list {0} already exists and is not an enabled selling list in {1}").format(
				name, currency
			)
		)
	frappe.get_doc(
		{
			"doctype": "Price List",
			"price_list_name": name,
			"currency": currency,
			"selling": 1,
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return name


def create_store_warehouse(company: str) -> str:
	return (
		frappe.get_doc({"doctype": "Warehouse", "warehouse_name": STORE_WAREHOUSE_NAME, "company": company})
		.insert(ignore_permissions=True)
		.name
	)


def set_owner_default_app(user: str):
	"""Where the site's default app is not Commera, only the owner who ran onboarding lands on it."""
	if frappe.db.get_single_value("System Settings", "default_app") == "commera":
		return
	if not frappe.db.get_value("User", user, "default_app"):
		frappe.db.set_value("User", user, "default_app", "commera")


def get_company_warehouse(company: str) -> str | None:
	"""ERPNext's default warehouse for the company ("Stores"), not the first one in the tree (in transit)."""
	if default_warehouse := frappe.get_cached_value("Company", company, "default_warehouse"):
		return default_warehouse
	warehouses = frappe.get_all(
		"Warehouse",
		filters={"company": company, "is_group": 0, "warehouse_type": ["!=", "Transit"]},
		pluck="name",
		limit=1,
	)
	return warehouses[0] if warehouses else None


def get_setup_status() -> dict:
	status, error = frappe.db.get_single_value(SETTINGS_DOCTYPE, "store_setup_status"), None
	if status == "running" and not is_job_enqueued(SETUP_JOB_ID) and not is_setup_being_queued():
		with latest_committed_reads():
			status = frappe.db.get_single_value(SETTINGS_DOCTYPE, "store_setup_status", for_update=True)
			if status == "failed":
				error = frappe.db.get_single_value(SETTINGS_DOCTYPE, "store_setup_error", for_update=True)
		if status == "running":
			status, error = "failed", _("Store setup stopped before it finished. Please try again.")
	elif status != "running" and frappe.is_setup_complete():
		status = "done"
	elif status == "failed":
		error = frappe.db.get_single_value(SETTINGS_DOCTYPE, "store_setup_error")
	return {"status": status or "idle", "error": error}


def is_setup_being_queued() -> bool:
	return bool(frappe.cache.get_value(SETUP_QUEUEING_CACHE_KEY))


def get_setup_stage() -> str | None:
	return frappe.cache.get_value(SETUP_STAGE_CACHE_KEY)


def set_setup_stage(stage: str | None):
	frappe.cache.set_value(SETUP_STAGE_CACHE_KEY, stage, expires_in_sec=SETUP_JOB_TIMEOUT)
	if stage:
		frappe.publish_realtime(
			SETUP_REALTIME_EVENT, {"status": "running", "stage": stage}, user=frappe.session.user
		)


def set_setup_status(status: str, error: str | None = None):
	frappe.db.set_single_value(SETTINGS_DOCTYPE, {"store_setup_status": status, "store_setup_error": error})


def queue_store_setup(setup_args: dict) -> dict:
	"""Mark setup running and enqueue its job; deduplicate keeps a second click from queueing another."""
	set_setup_status("running")
	set_setup_stage(None)
	# The job reaches the queue only after this request commits: until then, running without a job is not
	# a dead job.
	frappe.cache.set_value(SETUP_QUEUEING_CACHE_KEY, 1, expires_in_sec=SETUP_QUEUEING_SECONDS)
	frappe.enqueue(
		run_store_setup,
		queue="long",
		timeout=SETUP_JOB_TIMEOUT,
		job_id=SETUP_JOB_ID,
		deduplicate=True,
		enqueue_after_commit=True,
		setup_args=setup_args,
	)
	return {"status": "running", "error": None}


def run_store_setup(setup_args: dict):
	"""Background job, run as the owner who queued it: setup, then the Commera Settings a store sells with."""
	status, error = "done", None
	try:
		set_setup_stage("company")
		run_frappe_setup(setup_args)
		set_setup_stage("storefront")
		seed_commera_settings(setup_args["company_name"])
		set_setup_stage("payments")
		# The COD Mode of Payment was made before the company had a cash account to link.
		create_payment_modes()
		add_store_options()
	except Exception as exception:
		frappe.db.rollback()
		frappe.log_error(title="Commera store setup failed")
		message = frappe.response.get("setup_wizard_failure_message") or str(exception)
		status, error = "failed", _("Store setup failed: {0}").format(message)

	set_setup_status(status, error)
	# after_commit: the job runner commits on return, and a client that refetches must see the data.
	frappe.publish_realtime(
		SETUP_REALTIME_EVENT, {"status": status, "error": error}, user=frappe.session.user, after_commit=True
	)


def needs_password_setup(user: str | None = None) -> bool:
	"""True for an owner provisioned without a password (Frappe Cloud v1), who cannot sign back in later.

	Mirrors Frappe CRM: users who sign in through SSO, LDAP or the Frappe Cloud v2 dashboard are excluded.
	"""
	from frappe.integrations.frappe_providers.cloud_settings import is_v2_site

	user = user or frappe.session.user
	if has_password(user) or frappe.get_system_settings("disable_user_pass_login") or is_v2_site():
		return False
	if frappe.db.get_single_value("LDAP Settings", "enabled"):
		return False
	# Every user carries a `frappe` provider row, so only other providers mean SSO sign-in.
	return not frappe.db.exists(
		"User Social Login",
		{"parenttype": "User", "parent": user, "provider": ["!=", "frappe"], "userid": ["is", "set"]},
	)


def has_password(user: str) -> bool:
	"""User passwords are hashed `__Auth` rows with encrypted = 0, which get_decrypted_password skips."""
	auth = frappe.qb.Table("__Auth")
	return bool(
		frappe.qb.from_(auth)
		.select(auth.name)
		.where(
			(auth.doctype == "User")
			& (auth.name == user)
			& (auth.fieldname == "password")
			& (auth.encrypted == 0)
		)
		.limit(1)
		.run()
	)
