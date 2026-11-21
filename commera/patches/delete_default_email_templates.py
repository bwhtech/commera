import frappe
from frappe.utils import get_datetime

SHIPPED_VERSIONS = {
	"Order Confirmation": (
		"2025-05-21 13:15:39.209014",
		"2026-09-29 12:00:00",
		"2026-10-20 12:00:00",
		"2026-11-12 12:00:00",
	),
	"Order Cancellation": ("2025-05-21 13:30:13.212018", "2026-11-12 12:00:00"),
	"Item In Stock": ("2025-05-23 13:47:33.809844",),
}


def execute():
	for name, versions in SHIPPED_VERSIONS.items():
		template = frappe.db.get_value("Email Template", name, ["creation", "modified"], as_dict=True)
		if not template or not is_unedited(template, versions):
			continue
		try:
			frappe.delete_doc("Email Template", name, ignore_permissions=True)
		except frappe.LinkExistsError:
			continue


def is_unedited(template, versions) -> bool:
	return template.modified == template.creation or template.modified in {
		get_datetime(version) for version in versions
	}
