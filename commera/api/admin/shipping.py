# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe

from commera.api.admin.integrations import describe_integration, save_integration
from commera.shipping.providers import get_provider_class, get_provider_doctypes

PROFILE_DOCTYPE = "Shipping Provider Profile"
PROFILE_SETTINGS_FIELDNAME = "provider_settings"
WEBHOOK_PATH = "/api/method/commera.shipping.webhook.handle?provider={profile}"


def get_shipping_registry():
	"""Every registered carrier as an integration entry, in hook order, which is the order the cards render in."""
	return [get_shipping_entry(settings_doctype) for settings_doctype in get_provider_doctypes()]


def get_shipping_entry(settings_doctype: str) -> dict:
	provider_class = get_provider_class(settings_doctype)
	label = provider_class.label or settings_doctype
	return {
		"slug": frappe.scrub(label),
		"label": label,
		"blurb": provider_class.blurb,
		"settings_doctype": settings_doctype,
		"docs_url": provider_class.docs_url,
		"logo": provider_class.logo,
		"profile_doctype": PROFILE_DOCTYPE,
		"profile_settings_fieldname": PROFILE_SETTINGS_FIELDNAME,
		"webhook_path": WEBHOOK_PATH,
	}


def get_shipping_integration(slug: str):
	for integration in get_shipping_registry():
		if integration["slug"] == slug:
			return integration

	frappe.throw(frappe._("Unknown shipping provider {0}").format(slug))


@frappe.whitelist()
def get_shipping_integrations():
	"""Every carrier the store can ship with, whether it is live, and the fields behind its dialog."""
	frappe.only_for("System Manager")

	return [describe_integration(integration) for integration in get_shipping_registry()]


@frappe.whitelist(methods=["POST"])
def save_shipping_integration(slug: str, enabled: int | str, values: dict | str | None = None):
	"""Save one carrier's credentials and turn it on or off. Returns the refreshed card."""
	frappe.only_for("System Manager")

	return save_integration(
		get_shipping_integration(slug), enabled, frappe.parse_json(values) if values else {}
	)
