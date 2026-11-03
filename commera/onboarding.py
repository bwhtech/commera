import frappe
from frappe import _
from frappe.apps import DESK_APP_PATTERN
from frappe.core.doctype.installed_applications.installed_applications import (
	get_setup_wizard_completed_apps,
)
from frappe.desk.page.setup_wizard.setup_wizard import setup_complete, update_global_settings
from frappe.utils.background_jobs import is_job_enqueued
from frappe.utils.data import add_days, add_years, get_abbr, getdate

from commera.migrate import DEFAULT_EMAIL_TEMPLATES, create_payment_modes

SETTINGS_DOCTYPE = "Commera Settings"
DEFAULT_PRICE_LIST = "Standard Selling"
DEFAULT_CHART_OF_ACCOUNTS = "Standard"
SETUP_REALTIME_EVENT = "commera_store_setup"
SETUP_JOB_ID = "commera_store_setup"
SETUP_JOB_TIMEOUT = 1500
MAX_ABBR_LENGTH = 5
# Left reachable on purpose: the escape hatch if Commera's own setup keeps failing.
DESK_SETUP_WIZARD_PATH = "/desk/setup-wizard"

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


def redirect_owner_from_desk(context):
	"""Send the owner of a site that has not run setup to /commera, before the desk wizard opens."""
	request = getattr(frappe.local, "request", None)
	if not request or not DESK_APP_PATTERN.match(request.path) or request.path == DESK_SETUP_WIZARD_PATH:
		return
	if not frappe.is_setup_complete() and is_onboarding_pending():
		frappe.redirect("/commera")


def get_fiscal_year_start_month(country: str | None) -> int:
	return FISCAL_YEAR_START_MONTHS.get(country, 1)


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


def run_frappe_setup(args: dict):
	"""Run Frappe and ERPNext setup with `args` and fail loudly unless the company now exists."""
	# Once frappe's own stage counts as done (an earlier, failed run marks it), setup_complete skips it and
	# later stages read country/currency off System Settings: run it here so they find this store's region.
	if "frappe" in get_setup_wizard_completed_apps():
		update_global_settings(frappe._dict(args))
	setup_complete(args)

	if not frappe.db.exists("Company", args["company_name"]):
		raise RuntimeError(f"Setup did not create company {args['company_name']}")


def seed_commera_settings(company: str):
	"""Fill the mandatory Commera Settings fields, which any later save() would otherwise trip on."""
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	settings.company = company
	for fieldname, template in DEFAULT_EMAIL_TEMPLATES.items():
		settings.set(fieldname, settings.get(fieldname) or template)

	settings.default_price_list = settings.default_price_list or DEFAULT_PRICE_LIST
	settings.ecommerce_warehouse = settings.ecommerce_warehouse or get_company_warehouse(company)
	settings.save(ignore_permissions=True)


def get_company_warehouse(company: str) -> str | None:
	"""ERPNext's default warehouse for the company ("Stores"), not the first one in the tree (in transit)."""
	return frappe.get_cached_value("Company", company, "default_warehouse") or frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 0, "warehouse_type": ["!=", "Transit"]}, "name"
	)


def get_setup_status() -> dict:
	"""The job's own record on Commera Settings; a site set up some other way also counts as done."""
	status, error = frappe.db.get_single_value(SETTINGS_DOCTYPE, "store_setup_status"), None
	if status == "running" and not is_job_enqueued(SETUP_JOB_ID):
		# The worker died or the job was dropped: report it so the owner can retry.
		status, error = "failed", _("Store setup stopped before it finished. Please try again.")
	elif status != "running" and frappe.is_setup_complete():
		status = "done"
	elif status == "failed":
		error = frappe.db.get_single_value(SETTINGS_DOCTYPE, "store_setup_error")
	return {"status": status or "idle", "error": error}


def set_setup_status(status: str, error: str | None = None):
	frappe.db.set_single_value(SETTINGS_DOCTYPE, {"store_setup_status": status, "store_setup_error": error})


def queue_store_setup(args: dict) -> dict:
	"""Mark setup running and enqueue its job; deduplicate keeps a second click from queueing another."""
	set_setup_status("running")
	frappe.enqueue(
		run_store_setup,
		queue="long",
		timeout=SETUP_JOB_TIMEOUT,
		job_id=SETUP_JOB_ID,
		deduplicate=True,
		enqueue_after_commit=True,
		setup_args=args,
	)
	return {"status": "running", "error": None}


def run_store_setup(setup_args: dict):
	"""Background job, run as the owner who queued it: setup, then the Commera Settings a store sells with."""
	status, error = "done", None
	try:
		run_frappe_setup(setup_args)
		seed_commera_settings(setup_args["company_name"])
		# The COD Mode of Payment was made before the company had a cash account to link.
		create_payment_modes()
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
