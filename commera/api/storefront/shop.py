from urllib.parse import quote

import frappe
from frappe import _

from commera.api.storefront import rate_limited_guest_api
from commera.sdk import shop
from commera.sdk.types import ContentPage, ContentPageLink, Country, MenuItem, Sitemap


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_shop() -> dict:
	"""The shop, with each menu item's path on a headless storefront in `url`."""
	details = shop.get_shop()
	return {**details, "menu": [with_storefront_url(item) for item in details["menu"]]}


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_page(handle: str) -> ContentPage:
	if page := shop.get_page(handle):
		return page
	frappe.throw(_("Page {0} not found").format(handle), frappe.DoesNotExistError)


@rate_limited_guest_api("GET", limit=600, seconds=60)
def list_pages() -> list[ContentPageLink]:
	return shop.list_pages()


@rate_limited_guest_api("GET", limit=60, seconds=60)
def get_sitemap(kind: str | None = None, page: int = 1) -> Sitemap:
	return shop.get_sitemap(kind=kind or None, page=page)


@rate_limited_guest_api("GET", limit=600, seconds=60)
def list_countries() -> list[Country]:
	return shop.list_countries()


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


@rate_limited_guest_api("POST", limit=10, seconds=60 * 60)
def subscribe_to_newsletter(email: str) -> None:
	shop.subscribe_to_newsletter(email)
