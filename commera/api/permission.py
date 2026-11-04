import frappe

from commera.roles import COMMERA_ADMIN, COMMERA_USER


def has_app_permission(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if frappe.get_cached_value("User", user, "user_type") != "System User":
		return False
	return bool({COMMERA_ADMIN, COMMERA_USER, "System Manager"} & set(frappe.get_roles(user)))
