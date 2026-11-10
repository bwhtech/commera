import re
from urllib.parse import quote_plus

import frappe

from commera import seo
from commera.localization import (
	get_localization,
	get_localized_request,
	get_request_path,
	strip_language_prefix,
)

# Cart/account/login render per-user content and must never be indexed. Matched without the language prefix.
UTILITY_PATH_PATTERN = re.compile(r"^/(cart|account|login)(?:/|$)")

UTILITY_PAGE_NAMES = {"cart": "Cart", "account": "My Account", "login": "Login"}


def update_website_context(context):
	context.localization = get_localization()
	# Website Settings' `url` is the site address; it would hide the url() Jinja global.
	context.pop("url", None)
	keep_prefix_in_login_action()

	match = match_utility_path(get_request_path())
	if not match:
		return

	context.no_cache = 1
	context.seo = seo.build_page_seo({"noindex": 1}, display_name=UTILITY_PAGE_NAMES[match.group(1)])
	context.json_ld = []


def keep_prefix_in_login_action():
	"""Frappe's "Not Permitted" page returns a guest to request.path, which has no language prefix.
	It sets that login link in frappe.local.response, which overrides the page context."""
	page_context = (getattr(frappe.local, "response", None) or {}).get("context")
	if not page_context or not get_localized_request():
		return

	unprefixed_action = f"/login?redirect-to={quote_plus(frappe.local.request.path)}"
	if page_context.get("primary_action") == unprefixed_action:
		page_context["primary_action"] = f"/login?redirect-to={quote_plus(get_request_path())}"


def match_utility_path(path):
	_language, rest = strip_language_prefix(path, include_unpublished=True)
	return UTILITY_PATH_PATTERN.match(rest)
