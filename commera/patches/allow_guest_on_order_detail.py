import frappe

from commera.shop_themes.doctype.shop_theme_settings.shop_theme_settings import (
	LANG,
	clear_settings_cache,
	seed_default_routes,
)


def execute():
	"""Open the order detail page to a guest holding the private order link, and add /track-order."""
	# seed_default_routes only adds missing patterns, so the existing detail route keeps requires_auth 1.
	frappe.db.set_value(
		"Shop Themed Route",
		{"url_pattern": rf"^{LANG}/account/orders/detail$", "requires_auth": 1},
		"requires_auth",
		0,
		update_modified=False,
	)
	clear_settings_cache()
	seed_default_routes()
