"""Published Theme Layouts, cached under a SHA-256 of the rows' content.
Imports and writes that keep `modified` still change the key, so a key never maps to other content."""

import hashlib

import frappe
from frappe.query_builder import CustomFunction

KEY_PREFIX = "commera:theme_layout:"
# Keys of replaced versions are never computed again, so they only need to expire.
EXPIRES_IN_SEC = 60 * 60
Sha2 = CustomFunction("SHA2", ["value", "length"])


def get_published_layouts(theme_names, page) -> dict:
	"""{theme: its parsed published layout, or None}, from the cache when this content is in it."""
	key = get_cache_key(theme_names, page, read_versions(theme_names, page))
	if (layouts := frappe.cache.get_value(key)) is not None:
		return layouts
	rows = read_rows(theme_names, page)
	layouts = parse_layouts(theme_names, rows)
	frappe.cache.set_value(
		get_cache_key(theme_names, page, get_versions(rows)), layouts, expires_in_sec=EXPIRES_IN_SEC
	)
	return layouts


def read_versions(theme_names, page) -> list[dict]:
	"""Each row's name and the SHA-256 of its published layout, without reading the layout."""
	layout = frappe.qb.DocType("Theme Layout")
	return (
		frappe.qb.from_(layout)
		.select(layout.name, Sha2(layout.published_layout, 256).as_("fingerprint"))
		.where(layout.theme.isin(list(theme_names)))
		.where(layout.page == page)
		.orderby(layout.name)
		.run(as_dict=True)
	)


def read_rows(theme_names, page) -> list[dict]:
	return frappe.get_all(
		"Theme Layout",
		filters={"theme": ("in", theme_names), "page": page},
		fields=["name", "theme", "published_layout"],
		order_by="name",
	)


def get_versions(rows) -> list[dict]:
	"""The versions read_versions gives for these rows: SHA2 hashes the same UTF-8 bytes."""
	return [frappe._dict(name=row.name, fingerprint=get_fingerprint(row.published_layout)) for row in rows]


def parse_layouts(theme_names, rows) -> dict:
	stored = {row.theme: row.published_layout for row in rows}
	return {name: frappe.parse_json(stored[name]) if stored.get(name) else None for name in theme_names}


def get_cache_key(theme_names, page, versions) -> str:
	"""set_value and get_value scope the key to the site."""
	fingerprints = [[row.name, row.fingerprint] for row in versions]
	version = frappe.as_json([page, list(theme_names), fingerprints])
	return KEY_PREFIX + hashlib.sha256(version.encode()).hexdigest()


def get_fingerprint(published_layout) -> str | None:
	if published_layout is None:
		return None
	return hashlib.sha256(published_layout.encode()).hexdigest()
