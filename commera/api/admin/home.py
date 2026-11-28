# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.utils.data import cint

from commera.api.admin.integrations import is_profile_enabled
from commera.api.admin.payments import get_payment_registry
from commera.builder_themes.pages import get_home_page_preview
from commera.roles import COMMERA_ADMIN
from commera.shop_themes.doctype.shop_theme.shop_theme import (
	BUILDER_THEME_TYPE,
	get_shipped_preview,
	get_theme_context,
	resolve_active_theme,
)
from commera.storefront_access import SETTINGS_DOCTYPE, get_store_name

PUBLISH_ROLE = "System Manager"


def has_published_product() -> bool:
	return bool(frappe.db.exists("Style Attribute Variant", {"is_published": 1}))


def has_online_payments() -> bool:
	by_doctype: dict[str, list[str]] = {}
	for integration in get_payment_registry():
		by_doctype.setdefault(integration["profile_doctype"], []).append(integration["label"])
	for profile_doctype, labels in by_doctype.items():
		if frappe.db.table_exists(profile_doctype) and frappe.db.exists(
			profile_doctype, {"name": ["in", labels], "enabled": 1}
		):
			return True
	return False


def has_shipping(settings) -> bool:
	return bool(settings.shipping_rule or frappe.db.exists("Shipping Service", {"enabled": 1}))


def get_store_preview(theme: str | None) -> dict:
	if not theme:
		return {"image": None, "image_dark": None}

	theme_context = get_theme_context(theme)
	if theme_context["theme_type"] == BUILDER_THEME_TYPE and (image := get_home_page_preview(theme)):
		return {"image": image, "image_dark": image}

	captured = frappe.db.get_value("Shop Theme", theme, ["thumbnail", "thumbnail_dark"], as_dict=True)
	if captured and captured.thumbnail:
		image, image_dark = captured.thumbnail, captured.thumbnail_dark
	else:
		shipped = get_shipped_preview(theme, theme_context["apps"].get(theme))
		image, image_dark = shipped.get("light"), shipped.get("dark")
	return {"image": image, "image_dark": image_dark or image}


@frappe.whitelist(methods=["GET"])
def get_home():
	frappe.only_for((COMMERA_ADMIN, PUBLISH_ROLE))

	settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
	theme = resolve_active_theme()
	return {
		"published": bool(settings.storefront_published),
		"can_publish": PUBLISH_ROLE in frappe.get_roles(),
		"store_name": get_store_name(),
		"store_category": settings.store_category,
		"country": frappe.db.get_single_value("System Settings", "country"),
		"primary_color": settings.primary_color,
		"theme": theme,
		"theme_names": frappe.get_all("Shop Theme", pluck="name", order_by="theme_name asc"),
		"cod_enabled": bool(settings.cod_enabled),
		"preview": get_store_preview(theme),
		"tasks": {
			"products": has_published_product(),
			"payments": has_online_payments(),
			"shipping": has_shipping(settings),
			"brand": bool(frappe.get_cached_doc("Website Settings").banner_image),
		},
	}


@frappe.whitelist(methods=["POST"])
def set_storefront_published(published: int | str):
	frappe.only_for(PUBLISH_ROLE)

	frappe.db.set_single_value(SETTINGS_DOCTYPE, "storefront_published", cint(published))
	return {"published": bool(cint(published))}
