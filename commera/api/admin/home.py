# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.utils.data import cint

from commera.api.admin.integrations import is_profile_enabled
from commera.api.admin.payments import get_payment_registry
from commera.api.admin.theme_layout import EDITOR_ROLES
from commera.roles import is_commera_admin
from commera.shop_themes.doctype.shop_theme.shop_theme import get_theme_context, resolve_active_theme

SETTINGS_DOCTYPE = "Commera Settings"
PUBLISH_ROLE = "System Manager"


def has_published_product() -> bool:
	return bool(frappe.db.exists("Style Attribute Variant", {"is_published": 1}))


def has_online_payments() -> bool:
	return any(is_profile_enabled(integration) for integration in get_payment_registry())


def has_shipping(settings) -> bool:
	"""A delivery option on offer, or a store shipping rule, is enough for checkout to quote delivery."""
	return bool(settings.shipping_rule or frappe.db.exists("Shipping Service", {"enabled": 1}))


def get_brand_logo() -> str | None:
	return frappe.get_cached_doc("Website Settings").banner_image


def get_store_preview(theme: str) -> dict:
	"""The live theme's homepage thumbnail, which the theme editor saves on publish, and whether Home
	may capture a fresh one: only a Sections theme has a preview page to capture, and only an editor may."""
	image = frappe.db.get_value("Shop Theme", theme, "thumbnail")
	captured_on = image and frappe.db.get_value(
		"File",
		{"file_url": image, "attached_to_doctype": "Shop Theme", "attached_to_name": theme},
		"creation",
	)
	return {
		"image": image,
		"captured_on": captured_on,
		"can_capture": get_theme_context(theme)["theme_type"] == "Sections"
		and bool(set(EDITOR_ROLES) & set(frappe.get_roles())),
	}


@frappe.whitelist(methods=["GET"])
def get_home():
	"""What the Home screen needs: whether the store is live and which setup tasks are done."""
	if not is_commera_admin():
		raise frappe.PermissionError

	settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
	brand_logo = get_brand_logo()
	theme = resolve_active_theme()
	return {
		"published": bool(settings.storefront_published),
		"can_publish": PUBLISH_ROLE in frappe.get_roles(),
		"store_name": settings.store_name or frappe.get_cached_doc("Website Settings").app_name,
		"store_category": settings.store_category,
		"country": frappe.db.get_single_value("System Settings", "country"),
		"primary_color": settings.primary_color,
		# The brand card draws the store in a look matched to its theme, by name and by place in the list.
		"theme": theme,
		"theme_names": frappe.get_all("Shop Theme", pluck="name", order_by="theme_name asc"),
		"cod_enabled": bool(settings.cod_enabled),
		"preview": get_store_preview(theme),
		"tasks": {
			"products": has_published_product(),
			"payments": has_online_payments(),
			"shipping": has_shipping(settings),
			"brand": bool(brand_logo),
		},
	}


@frappe.whitelist(methods=["POST"])
def set_storefront_published(published: int | str):
	"""Open the storefront to visitors, or take it back to the coming-soon page."""
	frappe.only_for(PUBLISH_ROLE)

	frappe.db.set_single_value(SETTINGS_DOCTYPE, "storefront_published", cint(published))
	return {"published": bool(cint(published))}
