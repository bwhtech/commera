import re
from itertools import count
from urllib.parse import urlsplit

import frappe
from frappe import _

from commera.localization.routing import canonicalize_location, clean_path, get_canonical_path, is_same_site

GROUP = re.compile(r"\((?:[^()\\]|\\.)*\)")


def canonicalize_redirect_targets(doc, method=None):
	"""doc_events validate on Website Settings: a rule never targets the default language's prefix.
	Frappe re-applies rules unless its cache is used, and /x → /en/x would then loop."""
	for row in list(doc.get("route_redirects") or []):
		if not names_an_obsolete_prefix(row.target or ""):
			continue
		row.target = canonicalize_location(row.target)
		if points_at_itself(row.source, row.target):
			doc.remove(row)
			frappe.msgprint(
				_("Removed the redirect from {0}: its page is now served there.").format(row.source)
			)


def names_an_obsolete_prefix(target: str) -> bool:
	if not is_same_site(target):
		return False
	path = urlsplit(target).path
	return get_canonical_path(path) != clean_path(path)


def points_at_itself(source: str, target: str) -> bool:
	"""`/products/(.*)` → `/products/\\1`: every match redirects to the URL it came from."""
	groups = count(1)
	pattern = GROUP.sub(lambda _match: f"\\{next(groups)}", (source or "").strip("^$"))
	return clean_path(pattern) == clean_path(target)
