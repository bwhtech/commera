from frappe.utils.caching import http_cache

from commera.api.storefront import rate_limited_guest_api
from commera.localization.ui_strings import get_ui_strings

ONE_YEAR = 60 * 60 * 24 * 365


@rate_limited_guest_api("GET", limit=600, seconds=60)
@http_cache(max_age=ONE_YEAR)
def get_translations(lang: str) -> dict[str, str]:
	"""{source: translation} of UI strings in `lang`, with the merchant's overrides.
	Pages add `v`, the dictionary version, so a changed dictionary gets a new URL."""
	return get_ui_strings(lang)
