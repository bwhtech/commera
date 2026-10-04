# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils.jinja_globals import is_rtl

from commera.api.admin.orders import get_reporting_currency, get_reporting_currency_symbol
from commera.api.permission import has_app_permission
from commera.plugins.registry import get_visible_plugins

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/commera"
		raise frappe.Redirect

	if not has_app_permission():
		frappe.throw(_("You do not have access to the store dashboard."), frappe.PermissionError)

	currency = get_reporting_currency()

	# get_csrf_token issues the token into the session, so it must be committed to outlive this request.
	context.boot = frappe._dict(
		{
			"csrf_token": frappe.sessions.get_csrf_token(),
			# The SPA has no /api/method/frappe.boot call of its own, so the site's date and time
			# formats ride along on the shell instead of costing every screen an extra round trip.
			"date_format": frappe.db.get_default("date_format") or "yyyy-mm-dd",
			"time_format": frappe.db.get_default("time_format") or "HH:mm:ss",
			# The session language decides which way the whole shell reads, so the direction is
			# resolved by the framework here rather than guessed from a hardcoded default client-side.
			"lang": frappe.local.lang or "en",
			"is_rtl": is_rtl(),
			# The reporting currency is a site setting, not a per-request one, so it rides the shell
			# instead of every money surface having to carry the symbol down from its own endpoint.
			"currency": currency,
			"currency_symbol": get_reporting_currency_symbol(currency),
			"plugins": get_visible_plugins(frappe.session.user),
		}
	)
	frappe.db.commit()  # nosemgrep

	context.no_cache = 1
