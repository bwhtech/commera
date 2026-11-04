import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils.data import cint, cstr

from commera.sdk.format import save_resized_image


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=600, seconds=60)
def get_resized_image(path: str, width: int):
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = save_resized_image(cstr(path), cint(width))
