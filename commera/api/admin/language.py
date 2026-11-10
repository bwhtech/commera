# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from commera.api.permission import has_app_permission
from commera.localization import Language


def get_dashboard_language(user: str | None = None) -> str:
	"""The admin's own language, else the site's, else English."""
	user = user or frappe.session.user
	return frappe.get_cached_value("User", user, "language") or frappe.get_system_settings("language") or "en"


@frappe.whitelist(methods=["GET"])
def get_languages() -> dict:
	"""The enabled languages the admin can pick, each named in its own script."""
	ensure_dashboard_access()
	codes = frappe.get_all("Language", filters={"enabled": 1}, pluck="name", order_by="name")
	return {
		"current": get_dashboard_language(),
		"languages": [Language.from_code(code).as_dict() for code in codes],
	}


@frappe.whitelist(methods=["POST"])
def set_language(language: str) -> str:
	ensure_dashboard_access()
	if not frappe.db.exists("Language", {"name": language, "enabled": 1}):
		frappe.throw(_("{0} is not an enabled language.").format(language))

	# set_value skips the User controller, which would re-validate unrelated fields of the admin's record.
	frappe.db.set_value("User", frappe.session.user, "language", language)
	return language


def ensure_dashboard_access():
	if not has_app_permission():
		frappe.throw(_("You do not have access to the store dashboard."), frappe.PermissionError)
