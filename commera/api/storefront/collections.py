import frappe
from frappe import _

from commera.api.storefront import rate_limited_guest_api
from commera.sdk import catalog
from commera.sdk.types import Collection


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_collections() -> list[Collection]:
	return catalog.list_collections()


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_collection(handle: str) -> Collection:
	if collection := catalog.get_collection(handle):
		return collection
	frappe.throw(_("Collection {0} not found").format(handle), frappe.DoesNotExistError)
