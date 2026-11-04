import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from commera.sdk import catalog
from commera.sdk.types import Collection


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60)
def get_collections() -> list[Collection]:
	return catalog.list_collections()


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60)
def get_collection(handle: str) -> Collection:
	if collection := catalog.get_collection(handle):
		return collection
	frappe.throw(_("Collection {0} not found").format(handle), frappe.DoesNotExistError)
