# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from bwh_payments.api import GatewayInfo, get_gateways

from commera.api.admin.integrations import describe_integration, save_integration
from commera.api.payments import REUSABLE_CHECKOUT
from commera.migrate import add_payment_mode
from commera.plugin_events import get_handler_app, is_supported_app

PROFILE_DOCTYPE = "Payment Gateway Profile"
REQUIRED_GATEWAY_FIELDS = {"slug", "label", "settings_doctype"}
PROFILE_SETTINGS_FIELDNAME = "gateway_settings"
WEBHOOK_PATH = "/api/method/bwh_payments.bwh_payments.webhook.handle?gateway={profile}"


def add_gateway_payment_mode(integration):
	"""ERPNext refuses to post a Payment Entry for a gateway with no matching Mode of Payment."""
	add_payment_mode(integration["label"], "Bank")


def get_payment_gateways():
	"""bwh_payments' gateways, then each provider app's `commera_payment_gateways` card; a card cannot replace one."""
	gateways = [get_bwh_payments_card(gateway) for gateway in get_gateways()]
	slugs = {gateway["slug"] for gateway in gateways}
	for method in get_gateway_hooks():
		gateway = get_hook_gateway(method)
		if gateway and gateway["slug"] not in slugs:
			gateways.append(gateway)
			slugs.add(gateway["slug"])
	return gateways


def get_payment_registry():
	"""The gateway registry as integration entries, with what every payment gateway shares filled in."""
	return [
		{
			"capabilities": [],
			**gateway,
			"profile_doctype": PROFILE_DOCTYPE,
			"profile_settings_fieldname": PROFILE_SETTINGS_FIELDNAME,
			"webhook_path": WEBHOOK_PATH,
			"on_enable": add_gateway_payment_mode,
		}
		for gateway in get_payment_gateways()
	]


def get_gateways_with_capability(capability: str) -> list[str]:
	"""Payment Gateway Profile names whose provider declares `capability`."""
	return [
		gateway["label"]
		for gateway in get_payment_gateways()
		if capability in gateway.get("capabilities", ())
	]


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


def get_bwh_payments_card(gateway: GatewayInfo) -> dict:
	return {
		"slug": frappe.scrub(gateway.name),
		"label": gateway.name,
		"blurb": gateway.description,
		"settings_doctype": gateway.settings_doctype,
		"docs_url": gateway.docs_url,
		"capabilities": [REUSABLE_CHECKOUT] if gateway.reusable_checkout else [],
	}


def get_gateway_hooks() -> list[str]:
	return [
		method
		for method in frappe.get_hooks("commera_payment_gateways")
		if is_supported_app(get_handler_app(method))
	]


def get_hook_gateway(method: str) -> dict | None:
	# Read on every checkout, so a broken provider app is logged and skipped, never raised.
	try:
		gateway = frappe.get_attr(method)()
		if missing := REQUIRED_GATEWAY_FIELDS - set(gateway):
			raise ValueError(f"Gateway card is missing {', '.join(sorted(missing))}")
		return gateway
	except Exception:
		frappe.log_error(title=f"commera_payment_gateways hook failed: {method}"[:140], defer_insert=True)
		return None
