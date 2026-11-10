import re

import frappe

from commera.shop_themes.doctype.shop_theme_settings.shop_theme_settings import clear_settings_cache

# A stored pattern that starts with a language group, such as ^(?P<lang>en|ar)/products$.
LANGUAGE_GROUP_PREFIX = re.compile(r"^\^?\(\?P<lang>[^()]*\)/?")


def execute():
	"""Rewrite theme route patterns to match the path without its language prefix.
	A rewrite that repeats another row deletes it only when the rows route the same way."""
	rows = frappe.get_all(
		"Shop Themed Route",
		filters={"parent": "Shop Theme Settings", "parenttype": "Shop Theme Settings"},
		fields=["name", "url_pattern", "template_path", "requires_auth"],
		order_by="idx asc",
	)
	# Rows without the group keep their pattern, so they claim it before any rewrite does.
	claimed = {row.url_pattern: route_target(row) for row in rows if not has_language_group(row)}
	for row in rows:
		if has_language_group(row):
			rewrite_row(row, claimed)

	clear_settings_cache()


def rewrite_row(row, claimed: dict):
	pattern = drop_language_group(row.url_pattern)
	if pattern not in claimed:
		frappe.db.set_value("Shop Themed Route", row.name, "url_pattern", pattern, update_modified=False)
		claimed[pattern] = route_target(row)
	elif claimed[pattern] == route_target(row):
		frappe.db.delete("Shop Themed Route", row.name)
	else:
		# The other row serves this path now. Keep this one as stored, so no route is lost.
		print(f"Shop Theme Settings: {row.url_pattern} was kept: another route already uses {pattern}")
		frappe.log_error(
			"Theme route kept with its language group",
			f"{row.url_pattern} (template {row.template_path}) was not rewritten: "
			f"another route already uses {pattern}. Edit the routes in Shop Theme Settings.",
		)


def route_target(row) -> tuple[str, int]:
	return row.template_path or "", int(row.requires_auth or 0)


def has_language_group(row) -> bool:
	return drop_language_group(row.url_pattern) != (row.url_pattern or "")


def drop_language_group(pattern: str) -> str:
	return LANGUAGE_GROUP_PREFIX.sub("^", pattern or "", count=1)
