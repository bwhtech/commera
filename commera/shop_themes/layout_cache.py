"""Published Theme Layouts, cached under the (name, modified) of the rows they were read from.
Content is cached under the versions read in the same statement, so a key never maps to another version."""

import hashlib

import frappe

KEY_PREFIX = "commera:theme_layout:"
# Keys of replaced versions are never computed again, so they only need to expire.
EXPIRES_IN_SEC = 60 * 60


def get_published_layouts(theme_names, page) -> dict:
	"""{theme: its parsed published layout, or None}, from the cache when this version is in it."""
	key = get_cache_key(theme_names, page, read_rows(theme_names, page, ["name", "modified"]))
	if (layouts := frappe.cache.get_value(key)) is not None:
		return layouts
	rows = read_rows(theme_names, page, ["name", "modified", "theme", "published_layout"])
	layouts = parse_layouts(theme_names, rows)
	frappe.cache.set_value(get_cache_key(theme_names, page, rows), layouts, expires_in_sec=EXPIRES_IN_SEC)
	return layouts


def read_rows(theme_names, page, fields) -> list[dict]:
	"""The rows the page resolves through; every save changes a row's modified."""
	return frappe.get_all(
		"Theme Layout",
		filters={"theme": ("in", theme_names), "page": page},
		fields=fields,
		order_by="name",
	)


def parse_layouts(theme_names, rows) -> dict:
	stored = {row.theme: row.published_layout for row in rows}
	return {name: frappe.parse_json(stored[name]) if stored.get(name) else None for name in theme_names}


def get_cache_key(theme_names, page, rows) -> str:
	"""set_value and get_value scope the key to the site."""
	versions = [[row.name, str(row.modified)] for row in rows]
	version = frappe.as_json([page, list(theme_names), versions])
	return KEY_PREFIX + hashlib.sha256(version.encode()).hexdigest()
