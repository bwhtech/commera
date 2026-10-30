import frappe
from frappe import _

from commera.shipping.providers import get_provider


def get_provider_profile(provider_settings: str) -> str:
	"""The enabled Shipping Provider Profile backed by a settings Single."""
	profiles = frappe.get_all(
		"Shipping Provider Profile",
		filters={"provider_settings": provider_settings, "enabled": 1},
		pluck="name",
		limit=1,
	)
	if not profiles:
		frappe.throw(
			_("No enabled Shipping Provider Profile uses {0}.").format(frappe.bold(provider_settings))
		)
	return profiles[0]


def get_address_payload(address_name: str, contact_name: str | None = None) -> dict:
	"""One ERPNext Address in the shape ShippingProviderBase expects."""
	if not address_name:
		frappe.throw(_("An address is required to quote or book a shipment"))
	address = frappe.get_cached_doc("Address", address_name)
	return {
		"contact_name": contact_name or address.address_title,
		"company_name": address.address_title,
		"line1": address.address_line1,
		"line2": address.address_line2,
		"city": address.city,
		"state": address.state,
		"pincode": address.pincode,
		"country": address.country,
		"phone": address.phone,
		"email": address.email_id,
	}


def get_default_origin(provider: str) -> dict | None:
	"""Where a checkout quote ships from: the provider's `pickup_address`, by convention.
	A provider without that field has no default origin."""
	address_name = get_provider(provider).get("pickup_address")
	if not address_name:
		return None
	return get_address_payload(address_name)
