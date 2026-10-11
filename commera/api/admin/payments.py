# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe

from commera.api.admin.integrations import describe_integration, save_integration
from commera.migrate import add_payment_mode
from commera.plugin_events import get_handlers

PROFILE_DOCTYPE = "Payment Gateway Profile"
PROFILE_SETTINGS_FIELDNAME = "gateway_settings"
WEBHOOK_PATH = "/api/method/bwh_payments.bwh_payments.webhook.handle?gateway={profile}"

# Order here is the order the cards render in.
PAYMENT_GATEWAYS = (
	{
		"slug": "razorpay",
		"label": "Razorpay",
		"blurb": "Cards, UPI, netbanking and wallets. India.",
		"settings_doctype": "Razorpay Gateway Settings",
		"docs_url": "https://dashboard.razorpay.com/app/website-app-settings/webhooks",
	},
	{
		"slug": "stripe",
		"label": "Stripe",
		"blurb": "Cards and wallets, worldwide.",
		"settings_doctype": "Stripe Gateway Settings",
		"docs_url": "https://dashboard.stripe.com/apikeys",
	},
	{
		"slug": "telr",
		"label": "Telr",
		"blurb": "Cards and local methods across the GCC.",
		"settings_doctype": "Telr Gateway Settings",
		"docs_url": "https://telr.com/support/knowledge-base/hosted-payment-page-integration-guide/",
	},
	{
		"slug": "tabby",
		"label": "Tabby",
		"blurb": "Buy now, pay later in four instalments. MENA.",
		"settings_doctype": "Tabby Gateway Settings",
		"docs_url": "https://docs.tabby.ai/",
	},
)


def add_gateway_payment_mode(integration):
	"""ERPNext refuses to post a Payment Entry for a gateway with no matching Mode of Payment."""
	add_payment_mode(integration["label"], "Bank")


def get_payment_gateways():
	"""Built-ins, then `commera_hooks["payment_gateways"]` results; a hook cannot replace a built-in slug."""
	gateways = list(PAYMENT_GATEWAYS)
	slugs = {gateway["slug"] for gateway in gateways}
	for method in get_handlers("commera_hooks", "payment_gateways"):
		gateway = frappe.get_attr(method)()
		if gateway["slug"] not in slugs:
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
