from urllib.parse import quote

import frappe
from frappe import _

from commera.api.storefront import rate_limited_guest_api
from commera.localization import url
from commera.sdk import shop
from commera.sdk.types import (
	ContentPage,
	ContentPageLink,
	Country,
	Localization,
	MarketCountries,
	MenuItem,
	Sitemap,
)
from commera.storefront_cache import SHOP_DOMAINS, cached_guest_api


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_shop() -> dict:
	"""The shop and the resolved `localization`. Each menu item's `url` is its headless path,
	with the language prefix."""

	def _build():
		details = shop.get_shop()
		return {
			**details,
			"menu": [with_storefront_url(item) for item in details["menu"]],
			"localization": shop.get_localization(),
		}

	return cached_guest_api(
		"shop.get_shop",
		(),
		SHOP_DOMAINS,
		_build,
		endpoint="commera.api.storefront.shop.get_shop",
		ttl=300,
		cache_control="public, max-age=60, stale-while-revalidate=300",
	)


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_localization() -> Localization:
	"""The language that `_lang` resolves to, the default language and the published languages."""
	return cached_guest_api(
		"shop.get_localization",
		(),
		("shop",),
		shop.get_localization,
		endpoint="commera.api.storefront.shop.get_localization",
		ttl=300,
		cache_control="public, max-age=60, stale-while-revalidate=300",
	)


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_page(handle: str) -> ContentPage:
	def _build():
		if page := shop.get_page(handle):
			return page
		frappe.throw(_("Page {0} not found").format(handle), frappe.DoesNotExistError)

	return cached_guest_api(
		"shop.get_page",
		handle,
		("shop",),
		_build,
		endpoint="commera.api.storefront.shop.get_page",
		ttl=300,
		cache_control="public, max-age=60, stale-while-revalidate=300",
	)


@rate_limited_guest_api("GET", limit=600, seconds=60)
def list_pages() -> list[ContentPageLink]:
	return cached_guest_api(
		"shop.list_pages",
		(),
		("shop",),
		shop.list_pages,
		endpoint="commera.api.storefront.shop.list_pages",
		ttl=300,
		cache_control="public, max-age=60, stale-while-revalidate=300",
	)


@rate_limited_guest_api("GET", limit=60, seconds=60)
def get_sitemap(kind: str | None = None, page: int = 1) -> Sitemap:
	return cached_guest_api(
		"shop.get_sitemap",
		(kind or "", page),
		("catalog", "shop"),
		lambda: shop.get_sitemap(kind=kind or None, page=page),
		endpoint="commera.api.storefront.shop.get_sitemap",
		ttl=300,
		cache_control="public, max-age=60, stale-while-revalidate=300",
	)


@rate_limited_guest_api("GET", limit=600, seconds=60)
def list_countries() -> list[Country]:
	return cached_guest_api(
		"shop.list_countries",
		(),
		("shop",),
		shop.list_countries,
		endpoint="commera.api.storefront.shop.list_countries",
		ttl=300,
		cache_control="public, max-age=300, stale-while-revalidate=600",
	)


@rate_limited_guest_api("GET", limit=600, seconds=60)
def list_other_market_countries() -> list[MarketCountries]:
	return cached_guest_api(
		"shop.list_other_market_countries",
		(),
		("shop",),
		shop.list_other_market_countries,
		endpoint="commera.api.storefront.shop.list_other_market_countries",
		ttl=300,
		cache_control="public, max-age=300, stale-while-revalidate=600",
	)


def with_storefront_url(item: MenuItem) -> dict:
	return {
		**item,
		"url": get_storefront_url(item),
		"items": [with_storefront_url(child) for child in item["items"]],
	}


def get_storefront_url(item: MenuItem) -> str | None:
	return url(get_storefront_path(item))


def get_storefront_path(item: MenuItem) -> str | None:
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
