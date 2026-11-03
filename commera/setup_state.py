"""What a store has set up. The setup panel and the activation milestones both read these facts."""

import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Count
from frappe.utils.data import cint, cstr

from commera.api.admin.docfields import get_editable_docfields

DEFAULT_THEME = "Summer Theme"
PRODUCT_DOCTYPE = "Style Attribute Configurator"
STORE_SHIPPING_RULES = {"shipping_rule_type": "Selling"}
ENABLED = {"enabled": 1}


def count_products() -> int:
	"""A product is one configurator: the template and the options the dashboard edits together."""
	return frappe.db.count(PRODUCT_DOCTYPE)


def count_published_products() -> int:
	variant = DocType("Style Attribute Variant")
	return (
		frappe.qb.from_(variant)
		.select(Count(variant.configurator).distinct())
		.where(variant.is_published == 1)
		.run()[0][0]
	)


def count_enabled_gateways() -> int:
	return frappe.db.count("Payment Gateway Profile", ENABLED)


def is_cod_enabled() -> bool:
	return bool(cint(frappe.db.get_single_value("Commera Settings", "cod_enabled")))


def count_payment_methods() -> int:
	return count_enabled_gateways() + int(is_cod_enabled())


def count_shipping_rules() -> int:
	return frappe.db.count("Shipping Rule", STORE_SHIPPING_RULES)


def count_enabled_carriers() -> int:
	return frappe.db.count("Shipping Provider Profile", ENABLED)


def count_shipping_methods() -> int:
	return count_shipping_rules() + count_enabled_carriers()


def get_active_theme() -> str | None:
	return frappe.db.get_single_value("Shop Theme Settings", "active_theme")


def is_theme_customized() -> bool:
	"""The live theme is not the one Commera installs, or its layout or settings moved off the defaults."""
	theme = get_active_theme()
	if not theme:
		return False
	if theme != DEFAULT_THEME:
		return True
	if frappe.db.exists("Theme Layout", {"theme": theme, "published_layout": ("is", "set")}):
		return True
	return has_changed_theme_settings(frappe.db.get_value("Shop Theme", theme, "theme_settings"))


def has_changed_theme_settings(settings_doctype: str | None) -> bool:
	if not settings_doctype:
		return False
	settings = frappe.get_single(settings_doctype)
	return any(
		cstr(settings.get(docfield.fieldname)) != cstr(docfield.default)
		for _group_label, docfield in get_editable_docfields(settings_doctype)
	)


def get_setup_state() -> dict:
	return {
		"product": count_products() > 0,
		"payments": count_payment_methods() > 0,
		"shipping": count_shipping_methods() > 0,
		"theme": is_theme_customized(),
	}
