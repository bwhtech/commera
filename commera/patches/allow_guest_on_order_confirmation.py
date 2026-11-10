import frappe

from commera.shop_themes.doctype.shop_theme_settings.shop_theme_settings import (
	clear_settings_cache,
)

# Patterns from before the language prefix left the route table; drop_language_from_theme_routes rewrites them.
LANG = r"(?P<lang>en|ar)"


def execute():
	"""Open the gateway return URL to a logged-out shopper."""
	# seed_default_routes only adds missing patterns, so an existing route keeps its seeded requires_auth.
	frappe.db.set_value(
		"Shop Themed Route",
		{"url_pattern": rf"^{LANG}/account/orders/confirmation$", "requires_auth": 1},
		"requires_auth",
		0,
		update_modified=False,
	)
	clear_settings_cache()
