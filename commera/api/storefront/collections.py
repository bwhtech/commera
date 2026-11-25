import frappe
from frappe import _

from commera.api.storefront import rate_limited_guest_api
from commera.sdk import catalog
from commera.sdk.types import Collection
from commera.storefront_cache import cached_guest_api


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_collections() -> list[Collection]:
	return cached_guest_api(
		"collections.get_collections",
		(),
		("catalog", "shop"),
		catalog.list_collections,
		endpoint="commera.api.storefront.collections.get_collections",
		ttl=180,
		cache_control="public, max-age=30, stale-while-revalidate=120",
	)


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_collection(handle: str) -> Collection:
	def _build():
		if collection := catalog.get_collection(handle):
			return collection
		frappe.throw(_("Collection {0} not found").format(handle), frappe.DoesNotExistError)

	return cached_guest_api(
		"collections.get_collection",
		handle,
		("catalog", "shop"),
		_build,
		endpoint="commera.api.storefront.collections.get_collection",
		ttl=180,
		cache_control="public, max-age=30, stale-while-revalidate=120",
	)
