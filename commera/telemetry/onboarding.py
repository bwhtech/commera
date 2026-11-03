"""First-run onboarding events the server sees: the store setup job and the final step."""

import frappe
from frappe.utils import time_diff_in_seconds
from frappe.utils.data import cint, now_datetime

from commera import onboarding, setup_state
from commera.api.admin.settings import BRANDING_DOCTYPE, BRANDING_FIELDS
from commera.telemetry import (
	OTHER,
	bucket,
	capture,
	duration_bucket,
	error_kind,
	get_country_code,
	registry_value,
	seconds_since_install,
	telemetry_event,
	theme_value,
)

SETTINGS_DOCTYPE = "Commera Settings"
CHARTS_OF_ACCOUNTS = {"Standard": "standard", "Standard with Numbers": "standard_with_numbers"}
# The values of CATEGORIES in dashboard/src/ia/onboarding.js.
STORE_CATEGORIES = ("Fashion", "Beauty", "Home", "Food", "Electronics", "Other")
MINUTES_BUCKETS = ((5, "lt_5"), (15, "5_15"), (60, "15_60"))


@telemetry_event
def store_setup_started(args: dict, fiscal_year_start_month, company_abbr: str | None, previous_status: str):
	"""`fiscal_year_start_month` and `company_abbr` are what the owner sent, before any default fills them."""
	country = args["country"]
	requested_month = cint(fiscal_year_start_month)
	capture(
		"store_setup_started",
		country=get_country_code(country),
		currency=args["currency"],
		chart_of_accounts=CHARTS_OF_ACCOUNTS.get(args["chart_of_accounts"], OTHER),
		chart_overridden=args["chart_of_accounts"] != onboarding.DEFAULT_CHART_OF_ACCOUNTS,
		fiscal_month_overridden=bool(requested_month)
		and requested_month != onboarding.get_fiscal_year_start_month(country),
		abbr_overridden=bool(company_abbr)
		and company_abbr != onboarding.get_company_abbr(args["company_name"]),
		is_retry=previous_status == "failed",
	)


@telemetry_event
def store_setup_finished(queued_at, exception: BaseException | None):
	properties = {
		"outcome": "failed" if exception else "done",
		"duration_bucket": duration_bucket(
			time_diff_in_seconds(now_datetime(), queued_at) if queued_at else 0
		),
	}
	if exception:
		properties["error_kind"] = error_kind(exception)
	capture("store_setup_finished", **properties)


@telemetry_event
def onboarding_completed():
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	default_colour = frappe.get_meta(SETTINGS_DOCTYPE).get_field("primary_color").default
	capture(
		"onboarding_completed",
		store_category=registry_value(settings.store_category, STORE_CATEGORIES).lower(),
		has_logo=bool(frappe.db.get_single_value(BRANDING_DOCTYPE, BRANDING_FIELDS["brand_logo"])),
		custom_colour=bool(settings.primary_color) and settings.primary_color != default_colour,
		theme=theme_value(setup_state.get_active_theme()),
		cod_enabled=bool(settings.cod_enabled),
		guest_checkout_enabled=bool(settings.allow_guest_checkout),
		minutes_since_install=bucket(seconds_since_install() / 60, MINUTES_BUCKETS, "gt_60"),
	)
