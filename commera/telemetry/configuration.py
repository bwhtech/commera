"""Store configuration events: what a merchant switches on, and which registry entry it was."""

import frappe
from frappe.utils import date_diff

from commera.storefront_plugins import STOREFRONT_HOOKS
from commera.telemetry import capture, milestones, registry_value, rows_bucket, telemetry_event, theme_value

MISSING_FIELDS = "missing_fields"
# Storefront plugins Commera ships; any other app reports as `other`.
PLUGINS = ("commera_buy_links",)
# The values of Commera Discount.discount_type.
DISCOUNT_TYPES = ("amount_off_products", "amount_off_order", "buy_x_get_y", "free_shipping")
LIVE_MODE = "Live"


@telemetry_event
def get_integration_state(integration) -> frappe._dict:
	"""Read before an integration save: whether its profile is on, and since its last save."""
	state = frappe.db.get_value(
		integration["profile_doctype"], integration["label"], ["enabled", "modified"], as_dict=True
	)
	return state or frappe._dict(enabled=0, modified=None)


def is_switched_on(before, card) -> bool:
	return bool(before is not None and card["enabled"] and not before.enabled)


def is_switched_off(before, card) -> bool:
	return bool(before is not None and before.enabled and not card["enabled"])


@telemetry_event
def payment_gateway_saved(integration, before, card):
	gateway = integration["slug"]
	if is_switched_on(before, card):
		capture("payment_gateway_enabled", gateway=gateway, **get_live_mode(integration))
		milestones.payment_method_enabled(gateway)
	elif is_switched_off(before, card):
		days_enabled = date_diff(None, before.modified) if before.modified else 0
		capture("payment_gateway_disabled", gateway=gateway, days_enabled=days_enabled)


def get_live_mode(integration) -> dict:
	"""`live_mode` where the gateway settings carry a test flag, nothing where they do not."""
	settings = frappe.get_single(integration["settings_doctype"])
	if settings.meta.has_field("test_mode"):
		return {"live_mode": not settings.test_mode}
	if settings.meta.has_field("mode"):
		return {"live_mode": settings.mode == LIVE_MODE}
	return {}


@telemetry_event
def payment_gateway_save_failed(integration, exception: BaseException):
	reason = MISSING_FIELDS if isinstance(exception, frappe.MandatoryError) else "other"
	capture("payment_gateway_save_failed", gateway=integration["slug"], reason=reason)


@telemetry_event
def shipping_integration_saved(integration, before, card):
	if is_switched_on(before, card):
		capture("shipping_integration_enabled", carrier=integration["slug"])
		milestones.shipping_method_added()


@telemetry_event
def on_settings_update(doc, method=None):
	"""Cash on delivery switched in Settings → Payments, or anywhere else Commera Settings is saved."""
	if doc.get_doc_before_save() is None or not doc.has_value_changed("cod_enabled"):
		return
	capture("cod_toggled", enabled=bool(doc.cod_enabled))
	if doc.cod_enabled:
		milestones.payment_method_enabled(milestones.COD)


@telemetry_event
def shipping_rule_saved(rule):
	capture(
		"shipping_rule_saved",
		bands=len(rule.conditions),
		has_free_shipping=any(band.get("free_shipping") for band in rule.conditions),
	)


@telemetry_event
def theme_activated(previous_theme: str | None, theme: str):
	if previous_theme != theme:
		capture("theme_applied", theme=theme_value(theme))


@telemetry_event
def on_page_insert(doc, method=None):
	capture("storefront_page_created")


@telemetry_event
def on_discount_insert(doc, method=None):
	capture(
		"discount_created",
		type=registry_value(frappe.scrub(doc.discount_type or ""), DISCOUNT_TYPES),
		has_code=doc.method == "Code",
	)


@telemetry_event
def get_analytics_providers(settings) -> set[str]:
	"""Read before and after an Analytics Settings save."""
	providers = set()
	if settings.enable_ga4:
		providers.add("ga4")
	if settings.enable_facebook:
		providers.add("meta")
	if any(row.enabled for row in settings.custom_tracking_scripts):
		providers.add("custom_script")
	return providers


@telemetry_event
def analytics_saved(before: set[str] | None, settings):
	if before is None:
		return
	for provider in sorted(get_analytics_providers(settings) - before):
		capture("analytics_integration_enabled", provider=provider)


@telemetry_event
def on_app_install(app_name: str):
	"""An app that adds to the storefront is a storefront plugin."""
	if any(frappe.get_hooks(hook, None, app_name=app_name) for hook in STOREFRONT_HOOKS):
		capture("plugin_installed", plugin=registry_value(app_name, PLUGINS))


@telemetry_event
def products_imported(rows: int, created: int, errors: int):
	outcome = "failed" if not created else ("partial" if errors else "ok")
	capture("products_imported", rows_bucket=rows_bucket(rows), outcome=outcome)
