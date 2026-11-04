# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe

from commera.api.admin.integrations import describe_integration, save_integration
from commera.migrate import add_payment_mode
from commera.payment_gateways.connectors import get_connector_class, get_connector_doctypes

PROFILE_DOCTYPE = "Payment Gateway Profile"
PROFILE_SETTINGS_FIELDNAME = "gateway_settings"
WEBHOOK_PATH = "/api/method/commera.payment_gateways.api.handle_webhook?gateway={profile}"


def add_gateway_payment_mode(integration):
	"""ERPNext refuses to post a Payment Entry for a gateway with no matching Mode of Payment."""
	add_payment_mode(integration["label"], "Bank")


def get_payment_registry():
	return [get_payment_entry(settings_doctype) for settings_doctype in get_connector_doctypes()]


def get_payment_entry(settings_doctype: str) -> dict:
	connector = get_connector_class(settings_doctype)
	label = connector.label or settings_doctype
	return {
		"slug": frappe.scrub(label),
		"label": label,
		"blurb": connector.description,
		"settings_doctype": settings_doctype,
		"docs_url": connector.docs_url,
		"logo": connector.logo,
		"profile_doctype": PROFILE_DOCTYPE,
		"profile_settings_fieldname": PROFILE_SETTINGS_FIELDNAME,
		"webhook_path": WEBHOOK_PATH,
		"on_enable": add_gateway_payment_mode,
	}


def get_payment_integration(slug: str):
	for integration in get_payment_registry():
		if integration["slug"] == slug:
			return integration

	frappe.throw(frappe._("Unknown payment gateway {0}").format(slug))


@frappe.whitelist()
def get_payment_integrations():
	"""Every gateway the store can offer, whether it is live, and the fields behind its dialog."""
	frappe.only_for("System Manager")

	return [describe_integration(integration) for integration in get_payment_registry()]


@frappe.whitelist(methods=["POST"])
def save_payment_integration(slug: str, enabled: int | str, values: dict | str | None = None):
	"""Save one gateway's credentials and turn it on or off. Returns the refreshed card."""
	frappe.only_for("System Manager")

	return save_integration(
		get_payment_integration(slug), enabled, frappe.parse_json(values) if values else {}
	)
