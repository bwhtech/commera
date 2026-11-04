import frappe

from commera.roles import COMMERA_ADMIN, add_commera_roles


def execute():
	add_commera_roles()
	users = frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User", "name": ["not in", ["Administrator", "Guest"]]},
		pluck="name",
	)
	admins = set(
		frappe.get_all("Has Role", filters={"role": COMMERA_ADMIN, "parenttype": "User"}, pluck="parent")
	)
	for user in users:
		if user in admins or not frappe.has_permission("Item", "write", user=user):
			continue
		frappe.get_doc(
			{
				"doctype": "Has Role",
				"parent": user,
				"parenttype": "User",
				"parentfield": "roles",
				"role": COMMERA_ADMIN,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=user)
