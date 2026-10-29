# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe

from commera.api.admin.integrations import describe_integration, save_integration

PROFILE_DOCTYPE = "Shipping Provider Profile"
PROFILE_SETTINGS_FIELDNAME = "provider_settings"
WEBHOOK_PATH = "/api/method/bwh_shipping.bwh_shipping.webhook.handle?provider={profile}"

# Order here is the order the cards render in.
SHIPPING_PROVIDERS = (
	{
		"slug": "shiprocket",
		"label": "Shiprocket",
		"blurb": "Courier aggregator for domestic India. Pincode-driven, COD supported.",
		"settings_doctype": "Shiprocket Shipping Settings",
		"docs_url": "https://apidocs.shiprocket.in/",
	},
	{
		"slug": "aftership",
		"label": "AfterShip",
		"blurb": "Global labels and tracking across hundreds of carriers.",
		"settings_doctype": "AfterShip Shipping Settings",
		"docs_url": "https://www.aftership.com/docs/shipping/quickstart/api-quick-start",
	},
)


def get_shipping_registry():
	"""The carrier registry as integration entries, with what every carrier shares filled in."""
	return [
		{
			**provider,
			"profile_doctype": PROFILE_DOCTYPE,
			"profile_settings_fieldname": PROFILE_SETTINGS_FIELDNAME,
			"webhook_path": WEBHOOK_PATH,
		}
		for provider in SHIPPING_PROVIDERS
	]


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
