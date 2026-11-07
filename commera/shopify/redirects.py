import re

import frappe
from frappe.utils import cstr


def get_redirect_source(path: str) -> str:
	"""Frappe matches a redirect source as a regular expression against the path without slashes."""
	return re.escape(cstr(path).strip("/ "))


def save_redirects(redirects: dict[str, str]) -> int:
	"""Add or change Website Settings redirects. `redirects` maps an old path to its new target.
	Returns how many rows were added or changed."""
	redirects = {get_redirect_source(path): target for path, target in redirects.items() if path and target}
	if not redirects:
		return 0

	settings = frappe.get_single("Website Settings")
	rows_by_source = {row.source: row for row in settings.route_redirects}
	changed = 0
	for source, target in redirects.items():
		row = rows_by_source.get(source)
		if row and row.target == target:
			continue
		if row:
			row.target = target
		else:
			settings.append(
				"route_redirects", {"source": source, "target": target, "redirect_http_status": "301"}
			)
		changed += 1

	if changed:
		settings.save(ignore_permissions=True)
	return changed
