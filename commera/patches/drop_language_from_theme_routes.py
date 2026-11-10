import re

import frappe

from commera.shop_themes.doctype.shop_theme_settings.shop_theme_settings import clear_settings_cache

# A stored pattern that starts with a language group, such as ^(?P<lang>en|ar)/products$.
LANGUAGE_GROUP_PREFIX = re.compile(r"^\^?\(\?P<lang>[^()]*\)/?")


def execute():
	"""Rewrite theme route patterns to match the path without its language prefix.
	A rewrite that repeats an earlier row's pattern deletes the row instead of adding a duplicate."""
	seen = set()
	for row in frappe.get_all(
		"Shop Themed Route",
		filters={"parent": "Shop Theme Settings", "parenttype": "Shop Theme Settings"},
		fields=["name", "url_pattern"],
		order_by="idx asc",
	):
		pattern = drop_language_group(row.url_pattern)
		if pattern in seen:
			frappe.db.delete("Shop Themed Route", row.name)
		elif pattern != row.url_pattern:
			frappe.db.set_value("Shop Themed Route", row.name, "url_pattern", pattern, update_modified=False)
		seen.add(pattern)

	clear_settings_cache()


def drop_language_group(pattern: str) -> str:
	return LANGUAGE_GROUP_PREFIX.sub("^", pattern or "", count=1)
