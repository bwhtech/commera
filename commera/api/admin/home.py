# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

from zoneinfo import ZoneInfo

import frappe
from frappe.utils import get_system_timezone
from frappe.utils.data import cint

from commera.api.admin.integrations import is_profile_enabled
from commera.api.admin.payments import get_payment_registry
from commera.api.admin.theme_layout import EDITOR_ROLES
from commera.roles import COMMERA_ADMIN
from commera.shop_themes.doctype.shop_theme.shop_theme import get_theme_context, resolve_active_theme
from commera.storefront_access import SETTINGS_DOCTYPE, get_store_name

PUBLISH_ROLE = "System Manager"


def has_published_product() -> bool:
	return bool(frappe.db.exists("Style Attribute Variant", {"is_published": 1}))


def has_online_payments() -> bool:
	return any(is_profile_enabled(integration) for integration in get_payment_registry())


def has_shipping(settings) -> bool:
	return bool(settings.shipping_rule or frappe.db.exists("Shipping Service", {"enabled": 1}))


def get_store_preview(theme: str) -> dict:
	image = frappe.db.get_value("Shop Theme", theme, "thumbnail")
	captured_on = image and frappe.db.get_value(
		"File",
		{"file_url": image, "attached_to_doctype": "Shop Theme", "attached_to_name": theme},
		"creation",
	)
	return {
		"image": image,
		"captured_on": captured_on
		and captured_on.replace(tzinfo=ZoneInfo(get_system_timezone())).isoformat(),
		"can_capture": get_theme_context(theme)["theme_type"] == "Sections"
		and bool(set(EDITOR_ROLES) & set(frappe.get_roles())),
	}


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
