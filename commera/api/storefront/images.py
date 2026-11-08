import frappe
from frappe.utils.data import cint, cstr

from commera.api.storefront import rate_limited_guest_api
from commera.sdk.format import save_resized_image


@rate_limited_guest_api("GET", limit=600, seconds=60)
def get_resized_image(path: str, width: int):
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = save_resized_image(cstr(path), cint(width))
