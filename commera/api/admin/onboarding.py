import re

import frappe
from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import get_charts_for_country
from frappe import _
from frappe.core.doctype.user.user import get_timezones
from frappe.utils.data import cint, cstr

from commera import onboarding, setup_state
from commera.api.admin.settings import read_branding_fields, write_branding_fields
from commera.telemetry import milestones
from commera.telemetry import onboarding as onboarding_telemetry

SETTINGS_DOCTYPE = "Commera Settings"
ONBOARDING_ROLE = "System Manager"
HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")


def get_charts_of_accounts(country: str | None) -> list[str]:
	return get_charts_for_country(country or "", with_standard=True)


def get_options(country: str | None) -> dict:
	return {
		"countries": frappe.get_all("Country", pluck="name", order_by="name"),
		"currencies": frappe.get_all("Currency", pluck="name", order_by="name"),
		"time_zones": get_timezones()["timezones"],
		"charts_of_accounts": get_charts_of_accounts(country),
	}


def get_suggested_abbr(settings) -> str | None:
	"""The store company's own abbreviation once setup made it, else a free one for the store name."""
	if settings.company:
		return frappe.get_cached_value("Company", settings.company, "abbr")
	return onboarding.get_company_abbr(settings.store_name) if settings.store_name else None


@frappe.whitelist(methods=["GET"])
def get_onboarding():
	"""Everything the onboarding screens prefill, defaulted from what Frappe Cloud stored at signup."""
	frappe.only_for(ONBOARDING_ROLE)

	system_settings = frappe.get_single("System Settings")
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	user = frappe.get_cached_doc("User", frappe.session.user)
	country = system_settings.country
	return {
		"full_name": user.full_name,
		"email": user.email,
		"needs_password": onboarding.needs_password_setup(),
		"store_name": settings.store_name,
		"store_category": settings.store_category,
		"country": country,
		"currency": system_settings.currency,
		"time_zone": system_settings.time_zone,
		"chart_of_accounts": onboarding.DEFAULT_CHART_OF_ACCOUNTS,
		"fiscal_year_start_month": onboarding.get_fiscal_year_start_month(country),
		"company_abbr": get_suggested_abbr(settings),
		"is_frappe_setup_complete": frappe.is_setup_complete(),
		"setup": onboarding.get_setup_status(),
		"brand_logo": read_branding_fields()["brand_logo"],
		"primary_color": settings.primary_color,
		"cod_enabled": bool(settings.cod_enabled),
		"allow_guest_checkout": bool(settings.allow_guest_checkout),
		"options": get_options(country),
	}


@frappe.whitelist(methods=["GET"])
def get_country_defaults(country: str):
	"""What picking a country changes on the store step, so the screen never reads Frappe's geo data itself."""
	frappe.only_for(ONBOARDING_ROLE)
	from frappe.geo.country_info import get_country_info

	info = get_country_info(country) or {}
	return {
		"currency": info.get("currency"),
		"time_zone": (info.get("timezones") or [None])[0],
		"fiscal_year_start_month": onboarding.get_fiscal_year_start_month(country),
		"charts_of_accounts": get_charts_of_accounts(country),
	}


@frappe.whitelist(methods=["POST"])
def save_profile(full_name: str, password: str | None = None):
	"""The session user's own name, and a password only when one is given."""
	frappe.only_for(ONBOARDING_ROLE)

	full_name = cstr(full_name).strip()
	if not full_name:
		frappe.throw(_("Full name is required"), frappe.MandatoryError)

	user = frappe.get_doc("User", frappe.session.user)
	first_name, _space, last_name = full_name.partition(" ")
	user.first_name, user.last_name = first_name, last_name.strip()
	if password:
		# User.validate runs the site's password policy on new_password and hashes it on save.
		user.new_password = password
	user.save(ignore_permissions=True)
	return {"full_name": user.full_name, "needs_password": onboarding.needs_password_setup()}


def validate_store_setup(store_name, country, currency, time_zone, chart_of_accounts, start_month):
	if not store_name:
		frappe.throw(_("Store name is required"), frappe.MandatoryError)
	if not frappe.db.exists("Country", country):
		frappe.throw(_("Unknown country {0}").format(country))
	if not frappe.db.exists("Currency", currency):
		frappe.throw(_("Unknown currency {0}").format(currency))
	if time_zone not in get_timezones()["timezones"]:
		frappe.throw(_("Unknown time zone {0}").format(time_zone))
	if chart_of_accounts not in get_charts_of_accounts(country):
		frappe.throw(_("Chart of accounts {0} is not available for {1}").format(chart_of_accounts, country))
	if not 1 <= start_month <= 12:
		frappe.throw(_("Fiscal year start month must be between 1 and 12"))


@frappe.whitelist(methods=["POST"])
def start_store_setup(
	store_name: str,
	store_category: str,
	country: str,
	currency: str,
	time_zone: str,
	chart_of_accounts: str = onboarding.DEFAULT_CHART_OF_ACCOUNTS,
	fiscal_year_start_month: int | None = None,
	company_abbr: str | None = None,
):
	"""Save the store basics and queue the Frappe/ERPNext setup, once. A failed setup can be retried."""
	frappe.only_for(ONBOARDING_ROLE)

	# A running job is left alone: rewriting the settings under it would make its own save stale.
	status = onboarding.get_setup_status()
	if status["status"] == "running":
		return status

	store_name = cstr(store_name).strip()
	chart_of_accounts = chart_of_accounts or onboarding.DEFAULT_CHART_OF_ACCOUNTS
	start_month = cint(fiscal_year_start_month) or onboarding.get_fiscal_year_start_month(country)
	validate_store_setup(store_name, country, currency, time_zone, chart_of_accounts, start_month)
	company_abbr = cstr(company_abbr).strip().upper() or None
	if company_abbr and frappe.db.exists("Company", {"abbr": company_abbr}):
		frappe.throw(_("Abbreviation {0} is already used by another company").format(company_abbr))

	# set_single_value: the settings cannot save() until setup has made the company it requires.
	frappe.db.set_single_value(
		SETTINGS_DOCTYPE, {"store_name": store_name, "store_category": cstr(store_category).strip()}
	)
	if status["status"] == "done":
		return status

	args = onboarding.build_setup_args(
		store_name, country, currency, time_zone, chart_of_accounts, start_month, company_abbr
	)
	queued = onboarding.queue_store_setup(args)
	onboarding_telemetry.store_setup_started(args, fiscal_year_start_month, company_abbr, status["status"])
	return queued


@frappe.whitelist(methods=["GET"])
def get_setup_status():
	frappe.only_for(ONBOARDING_ROLE)
	return onboarding.get_setup_status()


@frappe.whitelist(methods=["POST"])
def save_brand(brand_logo: str | None = None, primary_color: str | None = None):
	frappe.only_for(ONBOARDING_ROLE)

	branding = write_branding_fields({"brand_logo": brand_logo} if brand_logo is not None else {})
	if primary_color and not HEX_COLOR.match(primary_color):
		frappe.throw(_("Primary color must be a hex color such as #1d4ed8"))
	if primary_color is not None:
		frappe.db.set_single_value(SETTINGS_DOCTYPE, "primary_color", primary_color)
	return {
		"brand_logo": branding["brand_logo"],
		"primary_color": frappe.db.get_single_value(SETTINGS_DOCTYPE, "primary_color"),
	}


@frappe.whitelist(methods=["POST"])
def save_selling(cod_enabled: int, allow_guest_checkout: int):
	frappe.only_for(ONBOARDING_ROLE)

	values = {"cod_enabled": cint(cod_enabled), "allow_guest_checkout": cint(allow_guest_checkout)}
	was_cod_enabled = milestones.get_cod_state()
	# set_single_value adds `modified` to the dict it is given, so it gets a copy.
	frappe.db.set_single_value(SETTINGS_DOCTYPE, dict(values))
	milestones.cod_saved(was_cod_enabled)
	return {key: bool(value) for key, value in values.items()}


@frappe.whitelist(methods=["POST"])
def complete_onboarding():
	frappe.only_for(ONBOARDING_ROLE)

	frappe.db.set_single_value(SETTINGS_DOCTYPE, "onboarding_completed", 1)
	onboarding_telemetry.onboarding_completed()
	return {"onboarding_completed": True}


@frappe.whitelist(methods=["GET"])
def get_setup_state():
	"""The four setup panel steps as booleans, from the same facts the activation milestones read."""
	frappe.has_permission(SETTINGS_DOCTYPE, ptype="read", throw=True)
	return setup_state.get_setup_state()
