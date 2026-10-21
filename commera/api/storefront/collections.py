import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.website.utils import cleanup_page_name


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60)
def get_collections() -> list[dict]:
	"""Every Item Group that holds a published product, as a storefront collection."""
	item_groups = get_listed_item_groups()
	rows = frappe.get_all(
		"Item Group",
		filters={"name": ("in", item_groups or [""])},
		fields=["name", "custom_displayname", "image", "modified"],
		order_by="custom_displayname asc",
	)
	return [get_collection_shape(row) for row in rows]


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60)
def get_collection(handle: str) -> dict:
	row = frappe.db.get_value(
		"Item Group",
		get_item_group(handle),
		["name", "custom_displayname", "image", "modified"],
		as_dict=True,
	)
	return get_collection_shape(row)


def get_item_group(handle: str) -> str:
	"""The listed Item Group behind a collection handle."""
	for item_group in get_listed_item_groups():
		if get_collection_handle(item_group) == handle:
			return item_group
	raise frappe.DoesNotExistError(_("Collection {0} not found").format(handle))


def get_listed_item_groups() -> list[str]:
	return frappe.get_all(
		"Style Attribute Variant",
		filters={"is_published": 1, "item_group": ("is", "set")},
		pluck="item_group",
		distinct=True,
	)


def get_collection_handle(item_group: str) -> str:
	return cleanup_page_name(item_group).replace("_", "-")


def get_collection_shape(row) -> dict:
	return {
		"handle": get_collection_handle(row.name),
		"title": row.custom_displayname or row.name,
		"image": row.image,
		"updated_at": str(row.modified),
	}
