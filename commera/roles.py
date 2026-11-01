import frappe
from frappe.core.doctype.doctype.doctype import validate_permissions_for_doctype
from frappe.permissions import setup_custom_perms

COMMERA_ADMIN = "Commera Admin"
COMMERA_USER = "Commera User"

ADMIN_PERMISSIONS = {
	"Item": ("read", "write", "create", "delete"),
	"Item Group": ("read", "write", "create"),
	"Item Attribute": ("read", "write", "create"),
	"Style Attribute Variant": ("read", "write", "create", "delete"),
	"Brand": ("read",),
	"Customer": ("read", "write"),
	"Sales Order": ("read", "write", "submit"),
	"Delivery Note": ("read", "create", "submit"),
	"Sales Invoice": ("read",),
	"Payment Entry": ("read",),
	"Stock Entry": ("read", "create", "submit"),
	"Stock Ledger Entry": ("read",),
	"Warehouse": ("read",),
	"Commera Discount": ("read", "write", "create", "delete"),
	"Product Review": ("read", "write"),
	"Shop Web Page": ("read", "write", "create", "delete"),
	"Ecommerce Category": ("read",),
	"Shop Theme Settings": ("read", "write"),
	"Commera Settings": ("read",),
}


def add_commera_roles():
	for role in (COMMERA_ADMIN, COMMERA_USER):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)

	for doctype, permission_types in ADMIN_PERMISSIONS.items():
		add_admin_permission(doctype, permission_types)


def add_admin_permission(doctype: str, permission_types: tuple[str, ...]):
	setup_custom_perms(doctype)
	if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": COMMERA_ADMIN, "permlevel": 0}):
		return

	frappe.get_doc(
		{
			"doctype": "Custom DocPerm",
			"parent": doctype,
			"parenttype": "DocType",
			"parentfield": "permissions",
			"role": COMMERA_ADMIN,
			"permlevel": 0,
			**dict.fromkeys(permission_types, 1),
		}
	).insert(ignore_permissions=True)
	validate_permissions_for_doctype(doctype)


def is_commera_admin(user: str | None = None) -> bool:
	return bool({COMMERA_ADMIN, "System Manager"} & set(frappe.get_roles(user)))
