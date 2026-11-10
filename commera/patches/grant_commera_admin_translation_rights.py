import frappe
from frappe.core.doctype.doctype.doctype import validate_permissions_for_doctype
from frappe.permissions import setup_custom_perms

from commera.roles import COMMERA_ADMIN, add_admin_permission

# Rights translation writes check. Granted once here; a migrate never grants them again.
TRANSLATION_RIGHTS = {
	"Theme Layout": ("read", "write", "create"),
	"Content Translation": ("read", "write", "create", "delete"),
}


def execute():
	# A site without the role gets these rights with it, from add_commera_roles.
	if not frappe.db.exists("Role", COMMERA_ADMIN):
		return
	for doctype, rights in TRANSLATION_RIGHTS.items():
		grant_rights(doctype, rights)


def grant_rights(doctype, rights):
	"""Set only the missing rights on Commera Admin's level 0 row, or add the row. Other roles,
	rights and restrictions stay as they are."""
	setup_custom_perms(doctype)
	key = {"parent": doctype, "role": COMMERA_ADMIN, "permlevel": 0}
	name = frappe.db.get_value("Custom DocPerm", key)
	if not name:
		add_admin_permission(doctype, rights)
		return
	granted = frappe.db.get_value("Custom DocPerm", name, list(rights), as_dict=True)
	if missing := {right: 1 for right in rights if not granted[right]}:
		frappe.db.set_value("Custom DocPerm", name, missing)
		validate_permissions_for_doctype(doctype)
