import frappe
from bwh_payments_core.engine import checkout, webhook
from frappe.rate_limiter import rate_limit


# nosemgrep: guest-whitelisted-method
@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=120, seconds=60, ip_based=True)
def handle_webhook():
	return webhook.handle()


@frappe.whitelist(methods=["POST"])
def retry_webhook(integration_request: str) -> None:
	webhook.retry_webhook(integration_request)


# nosemgrep: guest-whitelisted-method
@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=60, seconds=60, ip_based=True)
def return_from_gateway(request: str):
	checkout.return_from_gateway(request)
