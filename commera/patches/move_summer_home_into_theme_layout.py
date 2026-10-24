import frappe

from commera.shop_themes.doctype.theme_layout.theme_layout import save_theme_layout
from commera.shop_themes.summer_layout import (
	SUMMER_SETTINGS_DOCTYPE,
	build_summer_index_layout,
	get_summer_layout_themes,
)


def execute():
	settings = frappe.get_single(SUMMER_SETTINGS_DOCTYPE)
	for theme in get_summer_layout_themes():
		if frappe.db.exists("Theme Layout", {"theme": theme, "template": "index"}):
			continue
		try:
			save_theme_layout(
				theme,
				"index",
				build_summer_index_layout(settings, theme),
				ignore_permissions=True,
				synced_from_settings=True,
			)
		except frappe.ValidationError:
			frappe.log_error(
				title="Summer home could not move into Theme Layout",
				reference_doctype="Shop Theme",
				reference_name=theme,
			)
