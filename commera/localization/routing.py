from urllib.parse import quote, urlsplit

import frappe
from frappe.website.path_resolver import resolve_path
from werkzeug.routing.exceptions import RequestRedirect

from commera.localization.resolver import Localization, resolve
from commera.roles import is_commera_admin

ACCOUNT_PATH = "/account"
ACCOUNT_HOME_PATH = "/account/dashboard"

# Every store served English under /en/ before the default language moved to the root.
LEGACY_PREFIX = "en"


def resolve_website_path(path: str) -> str:
	"""website_path_resolver hook: a language prefix picks the language and is removed before routing.
	The URL alone decides the language, never the user, a cookie or Accept-Language."""
	path = "/" + path.strip("/ ")
	localization, rest = resolve(path, frappe.form_dict.get("_lang"), is_commera_admin())
	prefixed = rest != path
	prefix = get_canonical_prefix(localization, prefixed)
	redirect_to_canonical_path(path, prefix, rest if prefixed else strip_legacy_prefix(path))

	if prefix or is_storefront_path(path):
		frappe.local.lang = localization.language.code
	return route(rest, prefix)


def get_canonical_prefix(localization: Localization, prefixed: bool) -> str:
	"""The prefix a link to this page should carry: the default language has none."""
	if not prefixed or localization.language == localization.default_language:
		return ""
	return localization.root_prefix


def redirect_to_canonical_path(path: str, prefix: str, rest: str):
	if rest.rstrip("/") == ACCOUNT_PATH:
		rest = ACCOUNT_HOME_PATH

	target = prefix + rest
	if target.rstrip("/") != path.rstrip("/"):
		raise_redirect(target)


def strip_legacy_prefix(path: str) -> str:
	"""Drop /en/ when English is no open storefront language, so old links still land on the page."""
	segment, _slash, rest = path.strip("/").partition("/")
	return f"/{rest}" if segment.lower() == LEGACY_PREFIX else path


def route(rest: str, prefix: str) -> str:
	# Frappe's resolve_path sends "/" to the role home page, which is the desk for staff.
	if rest == "/":
		frappe.local.path = "index"
		return "index"

	try:
		return resolve_path(rest.strip("/"))
	except RequestRedirect as redirect:
		raise_redirect(prefix + urlsplit(redirect.new_url).path, redirect.code)


def raise_redirect(target: str, status_code: int = 301):
	# The path arrives percent-decoded: re-encode it, or a "?" in an item code starts the query string.
	target = quote(target, safe="/:,;=@!$&'()*+~")
	request = getattr(frappe.local, "request", None)
	query_string = frappe.safe_decode(request.query_string) if request else ""
	if query_string:
		target = f"{target}?{query_string}"
	frappe.flags.redirect_location = target
	raise frappe.Redirect(status_code)


def is_storefront_path(path: str) -> bool:
	from commera.storefront_access import is_storefront_path

	return is_storefront_path(path)
