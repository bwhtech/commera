import frappe

RATES_CACHE_PREFIX = "commera:carrier_rates:"


def clear_rates_cache(provider: str | None = None):
	frappe.cache.delete_keys(f"{RATES_CACHE_PREFIX}{provider + ':' if provider else ''}")
