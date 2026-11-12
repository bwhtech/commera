"""Drop the Custom DocPerm rows Commera made for its own doctypes, now that their JSON grants Commera
Admin. Only an exact copy of the doctype's DocPerm is dropped, so a merchant's changes stay."""

import frappe
from frappe.core.doctype.doctype.doctype import clear_permissions_cache
from frappe.permissions import reset_perms, rights

# The Commera doctypes that roles.ADMIN_PERMISSIONS listed before this patch.
COMMERA_DOCTYPES = (
	"Style Attribute Variant",
	"Commera Discount",
	"Product Review",
	"Shop Web Page",
	"Ecommerce Category",
	"Shop Theme Settings",
	"Commera Settings",
	"Commera Webhook",
	"Theme Layout",
	"Content Translation",
)
RULE_FIELDS = ("role", "permlevel", "if_owner", "mask", *rights)


def execute():
	for doctype in COMMERA_DOCTYPES:
		if not frappe.db.exists("Custom DocPerm", {"parent": doctype}):
			continue
		if get_rules("Custom DocPerm", doctype) != get_rules("DocPerm", doctype):
			print(f"{doctype}: kept its Custom DocPerm rows, which differ from the doctype's own")
			continue
		reset_perms(doctype)
		clear_permissions_cache(doctype)


def get_rules(permission_doctype: str, doctype: str) -> list[tuple]:
	rows = frappe.get_all(permission_doctype, filters={"parent": doctype}, fields=RULE_FIELDS)
	return sorted(tuple(row[field] or 0 for field in RULE_FIELDS) for row in rows)
