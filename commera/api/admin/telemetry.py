import frappe
from frappe import _

from commera.api.permission import has_app_permission
from commera.telemetry import dashboard


@frappe.whitelist(methods=["POST"])
def record_event(event: str, properties: dict | str | None = None):
	"""One dashboard event. Sent here rather than straight to Pulse so only known events and values go
	out, and so a page being closed can still send one (`keepalive`)."""
	if not has_app_permission():
		frappe.throw(_("You do not have access to the store dashboard."), frappe.PermissionError)
	if event not in dashboard.EVENTS:
		frappe.throw(_("Unknown dashboard event: {0}").format(event))
	dashboard.record(event, properties)
