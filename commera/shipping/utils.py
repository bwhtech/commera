import frappe
from frappe import _
from frappe.utils.caching import site_cache


@site_cache(ttl=60 * 60)
def get_available_shipping_providers() -> list[str]:
	# Profile on_update/on_trash clear only the worker that saved; the TTL bounds how long
	# other workers keep a stale list.
	return frappe.get_all("Shipping Provider Profile", filters={"enabled": 1}, pluck="name")


def resolve_provider(provider: str) -> str | None:
	"""Return the enabled Shipping Provider Profile matching a client-supplied name, case-insensitively."""
	requested = (provider or "").strip().casefold()
	if not requested:
		return None
	for profile in get_available_shipping_providers():
		if profile.casefold() == requested:
			return profile
	return None


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


def get_provider_controller(provider: str):
	"""The settings Single backing a profile, as a ShippingProviderBase."""
	settings = frappe.get_cached_value("Shipping Provider Profile", provider, "provider_settings")
	if not settings:
		frappe.throw(_("Shipping Provider Profile {0} has no settings doctype").format(frappe.bold(provider)))
	return frappe.get_single(settings)


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
	address_name = getattr(get_provider_controller(provider), "pickup_address", None)
	if not address_name:
		return None
	return get_address_payload(address_name)
