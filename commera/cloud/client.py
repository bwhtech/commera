import frappe
import requests
from frappe import _

from commera.cloud.link import retry_after_refusal

SITE_KEY_HEADER = "X-Commera-Site-Key"
TIMEOUT_SECONDS = 15


def is_linked() -> bool:
	settings = frappe.get_single("Commera Cloud Settings")
	return bool(settings.server_url and settings.site_key_value)


def call_cloud(method: str, data: dict | None = None) -> dict:
	"""Call a Commera Cloud service method with this site's key. A refused key queues a new link."""
	settings = frappe.get_single("Commera Cloud Settings")
	site_key = settings.site_key_value
	if not settings.server_url or not site_key:
		frappe.throw(_("This site is not linked to Commera Cloud."))

	response = requests.post(
		f"{settings.server_url}/api/method/{method}",
		json=data or {},
		headers={SITE_KEY_HEADER: site_key},
		timeout=TIMEOUT_SECONDS,
		allow_redirects=False,
	)
	if response.status_code == 401:
		retry_after_refusal()
	response.raise_for_status()
	return response.json()["message"]
