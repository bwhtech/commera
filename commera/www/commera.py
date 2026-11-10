# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.translate import get_all_translations

from commera.api.admin.language import get_dashboard_language
from commera.api.admin.orders import get_reporting_currency_symbol
from commera.api.permission import has_app_permission
from commera.localization import StorefrontLanguages
from commera.localization.languages import is_rtl_language
from commera.onboarding import is_onboarding_pending
from commera.plugins.registry import get_visible_plugins
from commera.roles import is_commera_admin
from commera.storefront_access import is_storefront_published
from commera.utils import get_store_currency

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/commera"
		raise frappe.Redirect

	context.boot = get_boot()
	context.no_cache = 1


@frappe.whitelist(methods=["GET"])
def get_context_for_dev():
	if not frappe.conf.developer_mode:
		frappe.throw(_("This method is only meant for developer mode"))
	return get_boot()


def get_boot():
	if not has_app_permission():
		frappe.throw(_("You do not have access to the store dashboard."), frappe.PermissionError)

	currency = get_store_currency()
	# A website request takes its language from the browser; the dashboard follows the admin instead.
	frappe.local.lang = get_dashboard_language()

	# get_csrf_token issues the token into the session, so it must be committed to outlive this request.
	boot = frappe._dict(
		{
			"csrf_token": frappe.sessions.get_csrf_token(),
			# The SPA has no /api/method/frappe.boot call of its own, so the site's date and time
			# formats ride along on the shell instead of costing every screen an extra round trip.
			"date_format": frappe.db.get_default("date_format") or "yyyy-mm-dd",
			"time_format": frappe.db.get_default("time_format") or "HH:mm:ss",
			# The language decides which way the whole shell reads, so the direction is
			# resolved by the framework here rather than guessed from a hardcoded default client-side.
			"lang": frappe.local.lang,
			"is_rtl": is_rtl_language(frappe.local.lang),
			# Every app's strings, so plugin pages translate through the same `__()` as the shell.
			"translations": get_all_translations(frappe.local.lang),
			# The reporting currency is a site setting, not a per-request one, so it rides the shell
			# instead of every money surface having to carry the symbol down from its own endpoint.
			"currency": currency,
			"currency_symbol": get_reporting_currency_symbol(currency),
			"plugins": get_visible_plugins(frappe.session.user),
			"is_admin": is_commera_admin(),
			"onboarding_pending": is_onboarding_pending(),
			"cloud_settings": get_cloud_settings(),
			"storefront_published": is_storefront_published(),
			# The theme editors preview every configured language, unpublished ones included.
			"storefront_languages": [
				language.as_dict() for language in StorefrontLanguages.load().configured
			],
		}
	)
	frappe.db.commit()  # nosemgrep
	return boot


def get_cloud_settings() -> dict:
	try:
		from frappe.integrations.frappe_providers.cloud_settings import get_boot_context
	except ImportError:  # Cloud Settings shipped with frappe v16
		return {"enabled": False}
	return get_boot_context()
