import frappe
from frappe import _
from frappe.utils.caching import site_cache

from commera.plugins import providers as registry
from commera.shipping.base_class import ShippingProviderBase

KIND = "shipping_providers"
PROFILE_DOCTYPE = "Shipping Provider Profile"


def get_provider_doctypes() -> list[str]:
	return registry.get_provider_doctypes(KIND)


def get_provider_class(settings_doctype: str) -> type[ShippingProviderBase]:
	return registry.get_provider_class(KIND, settings_doctype, ShippingProviderBase)


def get_provider(profile: str) -> ShippingProviderBase:
	"""The carrier behind a Shipping Provider Profile."""
	overrides = registry.get_provider_overrides(KIND)
	if overrides is not None:
		if profile not in overrides:
			frappe.throw(
				_("{0} is not a registered provider").format(frappe.bold(profile)),
				registry.ProviderNotRegisteredError,
			)
		return overrides[profile]

	settings_doctype = frappe.get_cached_value(PROFILE_DOCTYPE, profile, "provider_settings")
	if not settings_doctype:
		frappe.throw(_("Shipping Provider Profile {0} has no settings doctype").format(frappe.bold(profile)))
	get_provider_class(settings_doctype)
	return frappe.get_single(settings_doctype)


def use_providers(providers: dict[str, ShippingProviderBase]):
	"""Inside the block, only these Shipping Provider Profiles exist, backed by these objects."""
	return registry.use_providers(KIND, providers)


def get_enabled_profiles() -> list[str]:
	overrides = registry.get_provider_overrides(KIND)
	return list(overrides) if overrides is not None else get_available_shipping_providers()


@site_cache(ttl=60 * 60)
def get_available_shipping_providers() -> list[str]:
	# Profile on_update/on_trash clear only the worker that saved; the TTL bounds how long
	# other workers keep a stale list.
	return frappe.get_all(PROFILE_DOCTYPE, filters={"enabled": 1}, pluck="name")


def resolve_provider(provider: str) -> str | None:
	"""Return the enabled Shipping Provider Profile matching a client-supplied name, case-insensitively."""
	requested = (provider or "").strip().casefold()
	if not requested:
		return None
	for profile in get_enabled_profiles():
		if profile.casefold() == requested:
			return profile
	return None


def validate_providers(app_name: str | None = None):
	"""Runs after migrate and app install, so a broken carrier stops the operator, not a shopper."""
	problems = registry.get_provider_problems(KIND, ShippingProviderBase)
	registered = set(get_provider_doctypes())
	for profile in frappe.get_all(PROFILE_DOCTYPE, {"enabled": 1}, ["name", "provider_settings"]):
		if profile.provider_settings not in registered:
			problems.append(
				f"Shipping Provider Profile {profile.name} uses {profile.provider_settings}, which is not "
				"registered: its app is missing or built for another Commera API. Disable the profile."
			)

	if problems:
		frappe.throw("<br>".join(problems), registry.ProviderNotRegisteredError)


def disable_app_profiles(app_name: str):
	"""Uninstall drops the app's settings DocType, so its enabled profiles are switched off first."""
	for profile in frappe.get_all(PROFILE_DOCTYPE, {"enabled": 1}, ["name", "provider_settings"]):
		if registry.get_doctype_app(profile.provider_settings) != app_name:
			continue
		frappe.db.set_value(PROFILE_DOCTYPE, profile.name, "enabled", 0)
		message = f"Shipping Provider Profile {profile.name} was disabled because {app_name} was uninstalled."
		print(message)
		frappe.log_error(title="Shipping provider disabled", message=message)

	get_available_shipping_providers.clear_cache()
