from urllib.parse import urlsplit

import frappe
from frappe.website.utils import clear_cache

from commera.localization.routing import canonicalize_location, clean_path, get_canonical_path, is_same_site


def execute():
	"""Point Website Settings redirects at /en/... to the page at the root, where it is served now.
	website_redirects hooks are code, so their apps change them."""
	rows = frappe.get_all(
		"Website Route Redirect",
		filters={"parent": "Website Settings", "parenttype": "Website Settings"},
		fields=["name", "target"],
	)
	changed = [row for row in rows if names_an_obsolete_prefix(row.target or "")]
	for row in changed:
		target = canonicalize_location(row.target)
		frappe.db.set_value("Website Route Redirect", row.name, "target", target, update_modified=False)

	if changed:
		frappe.clear_document_cache("Website Settings", "Website Settings")
		clear_cache()


def names_an_obsolete_prefix(target: str) -> bool:
	if not is_same_site(target):
		return False
	path = urlsplit(target).path
	return get_canonical_path(path) != clean_path(path)
