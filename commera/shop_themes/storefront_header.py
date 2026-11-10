import frappe
from frappe.utils.data import cint

from commera.localization import Localization, get_localization
from commera.localization.formatter import Formatter
from commera.localization.ui_strings import get_ui_strings_version
from commera.utils import get_currency_symbols, get_store_currency


def render_storefront_header(localization: Localization | None = None) -> str:
	"""The page's storefront configuration and the storefront package bundle, for its <head>."""
	localization = localization or get_localization()
	return frappe.render_template(  # nosemgrep: frappe-ssti
		"templates/includes/commera-header-content.html",
		{
			"csrf_token": frappe.session.data.csrf_token,
			"store_currency": get_store_currency(),
			"currency_symbols": get_currency_symbols(),
			**Formatter(localization.language).as_config(),
			"language": localization.language.code,
			"localization": localization.as_dict(),
			"translations_version": get_ui_strings_version(localization.language.code),
			"webmcp": bool(
				cint(frappe.get_cached_value("Commera Settings", "Commera Settings", "enable_webmcp"))
			),
		},
	)
