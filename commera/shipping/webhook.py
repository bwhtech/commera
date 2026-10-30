import frappe
from frappe import _
from frappe.integrations.utils import create_request_log
from frappe.rate_limiter import rate_limit

from commera.shipping.providers import get_provider

WEBHOOK_ACCEPTED = {"status": "ok"}


# Carriers post unauthenticated; the carrier's own handle_webhook verifies the signature first.
@frappe.whitelist(allow_guest=True, methods=["POST"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=120, seconds=60, ip_based=True)
def handle():
	"""Public provider callback. Everything here is untrusted until the provider's own check clears it."""
	provider = frappe.request.args.get("provider")
	if not provider:
		return reject()

	profile = frappe.db.get_value(
		"Shipping Provider Profile", provider, ["name", "enabled", "provider_settings"], as_dict=True
	)
	if not profile or not profile.enabled:
		return reject()

	payload = frappe.request.get_data()
	headers = dict(frappe.request.headers)

	try:
		result = get_provider(profile.name).handle_webhook(payload, headers)
	except Exception:
		# The payload carries the customer's address and phone number, so only the provider and the
		# traceback are recorded.
		frappe.log_error(title=f"{provider} shipping webhook verification failed")
		log_webhook(provider, status="Failed")
		return reject()

	if not result:
		log_webhook(provider, status="Completed")
		return WEBHOOK_ACCEPTED

	awb = result.get("awb")
	status = result.get("status")
	event_id = result.get("event_id")

	if not (awb and status):
		log_webhook(provider, event_id=event_id, status="Failed")
		return WEBHOOK_ACCEPTED

	shipment_name = frappe.db.get_value("Shipment", {"awb_number": awb, "docstatus": 1}, "name")
	if not shipment_name:
		log_webhook(provider, awb=awb, event_id=event_id, status="Failed")
		return WEBHOOK_ACCEPTED

	shipment = frappe.get_doc("Shipment", shipment_name)
	if shipment.custom_shipping_provider != provider:
		frappe.log_error(
			title=f"{provider} shipping webhook provider mismatch",
			message=f"URL provider: {provider}, shipment provider: {shipment.custom_shipping_provider}",
		)
		log_webhook(provider, awb=awb, event_id=event_id, status="Failed")
		return reject()

	apply_status_as_administrator(
		shipment, status, event_id, result.get("events"), result.get("provider_status")
	)
	log_webhook(provider, awb=awb, event_id=event_id, status="Completed")
	# A replayed delivery is still a success as far as the provider is concerned; anything else and it
	# keeps retrying forever.
	return WEBHOOK_ACCEPTED


def apply_status_as_administrator(
	shipment,
	status: str,
	event_id: str | None,
	events: list | None,
	provider_status: str | None = None,
):
	# The callback runs as Guest, but the Sales Order write-back needs a real user. Restore the
	# user so a long-lived worker does not keep Administrator.
	session_user = frappe.session.user
	try:
		frappe.set_user("Administrator")  # nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
		shipment.apply_webhook_status(
			status, event_id=event_id, events=events, provider_status=provider_status
		)
	finally:
		frappe.set_user(session_user)  # nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser


def reject() -> dict:
	"""One opaque 400 for every verification failure, so a caller cannot probe configured providers.
	Clearing the message log stops a verifier's `frappe.throw` from leaking in `_server_messages`."""
	frappe.local.message_log = []
	frappe.local.response["http_status_code"] = 400
	return {"status": "error", "message": _("Webhook could not be verified")}


def log_webhook(provider: str, awb: str | None = None, event_id: str | None = None, status: str = "Queued"):
	create_request_log(
		{"provider": provider, "awb": awb, "event_id": event_id},
		service_name=f"{provider} Shipping Webhook",
		status=status,
		reference_doctype="Shipment",
	)
