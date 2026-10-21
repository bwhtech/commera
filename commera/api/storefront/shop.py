from urllib.parse import quote

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from commera.sdk import shop
from commera.sdk.types import ContentPage, MenuItem, SitemapEntry


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60)
def get_shop() -> dict:
	"""The shop, with each menu item's path on a headless storefront in `url`."""
	details = shop.get_shop()
	return {**details, "menu": [with_storefront_url(item) for item in details["menu"]]}


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60)
def get_page(handle: str) -> ContentPage:
	if page := shop.get_page(handle):
		return page
	raise frappe.DoesNotExistError(_("Page {0} not found").format(handle))


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=60, seconds=60)
def get_sitemap() -> dict[str, list[SitemapEntry]]:
	return shop.get_sitemap()


def with_storefront_url(item: MenuItem) -> dict:
	return {
		**item,
		"url": get_storefront_url(item),
		"items": [with_storefront_url(child) for child in item["items"]],
	}


def get_storefront_url(item: MenuItem) -> str | None:
	if item["type"] == "url":
		return item["target"]
	if item["type"] == "brand":
		return f"/search?q={quote(item['target'])}"
	if item["type"] == "collection":
		return f"/collections/{item['target']}"
	return "/collections/all" if item["type"] == "all" else None
