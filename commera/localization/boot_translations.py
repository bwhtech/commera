import frappe
from frappe.translate import get_all_languages, get_all_translations
from frappe.utils import get_build_version
from frappe.utils.caching import http_cache

try:
	from frappe.translate import get_boot_translations as get_frappe_boot_translations
	from frappe.translate import get_translation_version as get_frappe_translation_version
except ImportError:
	get_frappe_boot_translations = None
	get_frappe_translation_version = None

ONE_YEAR = 60 * 60 * 24 * 365
TRANSLATION_VERSION_KEY = "commera_translation_version"


def get_translation_version() -> str:
	if get_frappe_translation_version:
		return get_frappe_translation_version()
	version = frappe.cache.get_value(TRANSLATION_VERSION_KEY)
	if version is None:
		version = frappe.generate_hash(length=8)
		frappe.cache.set_value(TRANSLATION_VERSION_KEY, version)
	return f"{version}_{get_build_version()}"


def clear_translation_version():
	frappe.cache.delete_value(TRANSLATION_VERSION_KEY)


@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep: guest-whitelisted-method
@http_cache(max_age=ONE_YEAR)
def get_boot_translations(lang: str | None = None) -> dict[str, str]:
	if get_frappe_boot_translations:
		return get_frappe_boot_translations(lang)
	if lang and lang not in get_all_languages():
		lang = None
	return get_all_translations(lang or frappe.local.lang)
