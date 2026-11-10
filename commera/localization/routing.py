from urllib.parse import quote, urlsplit

import frappe
from frappe.website.path_resolver import resolve_path
from werkzeug.routing.exceptions import RequestRedirect

from commera.localization.resolver import Localization, LocalizedRequest, get_localized_request, resolve
from commera.roles import is_commera_admin

ACCOUNT_PATH = "/account"
ACCOUNT_HOME_PATH = "/account/dashboard"

# Every store served English under /en/ before the default language moved to the root.
LEGACY_PREFIX = "en"

# Requests that frappe.app.application never sends to the website router.
NON_PAGE_PATH_PREFIXES = ("/api/", "/assets/", "/backups", "/files/", "/private/files/", "/.well-known/")
PAGE_METHODS = ("GET", "HEAD", "POST")


def localize_request():
	"""before_request hook: a storefront page takes its language from the URL alone.
	Strips the prefix off request.path, so every app's website_path_resolver routes without it."""
	request = getattr(frappe.local, "request", None)
	if not request or not is_page_request(request):
		return

	localized = localize_path(request.path)
	if not localized:
		return

	request.commera_localized = localized
	frappe.local.lang = localized.localization.language.code
	if localized.route_path == "/":
		# Frappe's get_home_page() would send staff to the desk.
		frappe.local.flags.home_page = "index"
	set_request_path(request, localized.route_path)


def resolve_website_path(path: str) -> str:
	"""website_path_resolver hook: sends the redirect to the canonical URL, then routes.
	A redirect raised here wins over every other app's resolver, whatever the app order."""
	path = clean_path(path)
	localized = get_localized_request()
	if localized and path == localized.route_path and localized.redirect_to:
		raise_redirect(localized.redirect_to)

	# Frappe's resolve_path sends "/" to the role home page, which is the desk for staff.
	if path == "/":
		frappe.local.path = "index"
		return "index"
	prefix = localized.canonical_prefix if localized and path == localized.route_path else ""
	return route(path, prefix)


def localize_path(requested_path: str) -> LocalizedRequest | None:
	"""The localization of a storefront page path, or None for a page outside the storefront."""
	path = clean_path(requested_path)
	localization, rest = resolve(path, include_unpublished=is_commera_admin())
	rest = clean_path(rest)
	if not is_page_path(rest):
		return None

	prefixed = rest != path
	unprefixed = rest if prefixed else strip_legacy_prefix(path)
	if not prefixed and unprefixed == path and not is_storefront_path(path):
		return None

	prefix = get_canonical_prefix(localization, prefixed)
	return LocalizedRequest(
		path=requested_path,
		route_path=rest,
		localization=localization,
		canonical_prefix=prefix,
		redirect_to=get_redirect_target(path, prefix, unprefixed),
	)


def get_canonical_prefix(localization: Localization, prefixed: bool) -> str:
	"""The prefix a link to this page should carry: the default language has none."""
	if not prefixed or localization.language == localization.default_language:
		return ""
	return localization.root_prefix


def get_redirect_target(path: str, prefix: str, rest: str) -> str | None:
	if rest.rstrip("/") == ACCOUNT_PATH:
		rest = ACCOUNT_HOME_PATH

	target = clean_path(prefix + rest)
	return target if target != path else None


def strip_legacy_prefix(path: str) -> str:
	"""Drop /en/ when English is no open storefront language, so old links still land on the page."""
	segment, _slash, rest = path.strip("/").partition("/")
	return clean_path(rest) if segment.lower() == LEGACY_PREFIX else path


def route(path: str, prefix: str) -> str:
	try:
		return resolve_path(path.strip("/"))
	except RequestRedirect as redirect:
		raise_redirect(prefix + urlsplit(redirect.new_url).path, redirect.code)


def raise_redirect(target: str, status_code: int = 301):
	# The path arrives percent-decoded: re-encode it, or a "?" in an item code starts the query string.
	target = quote(clean_path(target), safe="/:,;=@!$&'()*+~")
	request = getattr(frappe.local, "request", None)
	query_string = frappe.safe_decode(request.query_string) if request else ""
	if query_string:
		target = f"{target}?{query_string}"
	frappe.flags.redirect_location = target
	raise frappe.Redirect(status_code)


def clean_path(path: str) -> str:
	"""`path` with exactly one leading slash. "//host" or "/\\host" would send a redirect off-site."""
	return "/" + (path or "").strip(" ").strip("/\\")


def set_request_path(request, path: str):
	# werkzeug caches these off request.path: read them first, so they keep the URL as requested.
	_cached = request.url, request.base_url, request.full_path
	request.path = path


def is_page_request(request) -> bool:
	return request.method in PAGE_METHODS and not frappe.form_dict.cmd and is_page_path(request.path)


def is_page_path(path: str) -> bool:
	return not (path.rstrip("/") + "/").startswith(NON_PAGE_PATH_PREFIXES)


def is_storefront_path(path: str) -> bool:
	from commera.storefront_access import is_storefront_path

	return is_storefront_path(path)
