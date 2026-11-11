from urllib.parse import urlsplit

import frappe

from commera.localization.routing import canonicalize_location, clean_path, get_canonical_path, is_same_site


def canonicalize_redirect_targets(doc, method=None):
	"""doc_events validate on Website Settings: point a target under the default language's
	prefix at the root, where the page is served, so the rule takes one hop."""
	if not frappe.db.table_exists("Commera Storefront Language"):
		return
	for row in doc.get("route_redirects") or []:
		if names_an_obsolete_prefix(row.target or ""):
			row.target = canonicalize_location(row.target)


def names_an_obsolete_prefix(target: str) -> bool:
	if not is_same_site(target):
		return False
	path = urlsplit(target).path
	return get_canonical_path(path) != clean_path(path)
