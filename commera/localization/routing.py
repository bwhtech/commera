import re
from urllib.parse import quote, urlsplit

import frappe
from frappe.website.path_resolver import resolve_path, resolve_redirect
from werkzeug.routing.exceptions import RequestRedirect

from commera.localization.languages import StorefrontLanguages
from commera.localization.resolver import (
	Localization,
	LocalizedRequest,
	get_localized_request,
	resolve,
	strip_language_prefix,
)
from commera.roles import is_commera_admin

ACCOUNT_PATH = "/account"
ACCOUNT_HOME_PATH = "/account/dashboard"

# Every store served English under /en/ before the default language moved to the root.
LEGACY_PREFIX = "en"

# Requests that frappe.app.application never sends to the website router, and Desk.
NON_PAGE_PATH_PREFIXES = (
	"/api/",
	"/app/",
	"/assets/",
	"/backups",
	"/desk/",
	"/files/",
	"/private/",
	"/socket.io/",
	"/.well-known/",
)
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
	# Redirect before any app's path resolver runs: another app's resolver may raise first.
	if redirect := get_website_redirect(localized):
		raise StorefrontRedirect(*redirect)
	if localized.redirect_to:
		raise StorefrontRedirect(encode_target(localized.redirect_to))

	if localized.route_path == "/":
		# Frappe's get_home_page() would send staff to the desk.
		frappe.local.flags.home_page = "index"
	skip_frappe_redirects(localized.route_path)
	set_request_path(request, localized.route_path)


class StorefrontRedirect(RequestRedirect):
	"""Raised in before_request: frappe.app sends the response of an HTTPException as it is."""

	def __init__(self, location: str, code: int = 301):
		super().__init__(location)
		self.code = code


def resolve_website_path(path: str) -> str:
	"""website_path_resolver hook: routes the path that localize_request stripped of its prefix."""
	path = clean_path(path)
	localized = get_localized_request()
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

	# Frappe's router would answer a doubled slash with its own redirect, which drops the prefix.
	target = clean_path(re.sub(r"/{2,}", "/", prefix + rest))
	return target if target != path else None


def get_website_redirect(localized: LocalizedRequest) -> tuple[str, int] | None:
	"""A website_redirects or Website Settings rule for the requested path, else for the path
	without its prefix. A same-site target of such an unprefixed rule keeps the language."""
	candidates = [(localized.path, "")]
	if localized.route_path != clean_path(localized.path):
		candidates.append((localized.route_path, localized.canonical_prefix))

	for path, prefix in candidates:
		if not (redirect := match_website_redirect(path)):
			continue
		# /en/... named the default language's page before it moved to the root.
		location = keep_language_prefix(canonicalize_location(redirect[0]), prefix)
		if not is_self_redirect(location, localized.path):
			return location, redirect[1]
	return None


def is_self_redirect(location: str, requested_path: str) -> bool:
	"""A rule written for /en/... would send the page back to itself. A new query string is a move."""
	if not is_same_site(location):
		return False
	target = urlsplit(location)
	query_string = frappe.safe_decode(frappe.local.request.query_string or b"")
	same_query = target.query in ("", query_string)
	return target.path == get_canonical_path(requested_path) and same_query


def match_website_redirect(path: str) -> tuple[str, int] | None:
	try:
		resolve_redirect(path.strip("/ "), frappe.local.request.query_string)
	except frappe.Redirect as redirect:
		return frappe.flags.redirect_location, redirect.http_status_code
	return None


def keep_language_prefix(location: str, prefix: str) -> str:
	if not prefix or not is_same_site(location):
		return location
	if strip_language_prefix(urlsplit(location).path, include_unpublished=True)[0]:
		return location
	return prefix + location


def canonicalize_location(location: str) -> str:
	"""A same-site `location` without the default language's prefix, which only redirects."""
	if not is_same_site(location):
		return location
	parts = urlsplit(location)
	return parts._replace(path=get_canonical_path(parts.path)).geturl()


def get_canonical_path(path: str) -> str:
	"""`path` as a link for guests: no prefix for the default language, and no closed /en/."""
	path = clean_path(path)
	language, rest = strip_language_prefix(path)
	if not language:
		return strip_legacy_prefix(path)
	return rest if language == StorefrontLanguages.load().default else path


def is_same_site(location: str) -> bool:
	return location.startswith("/") and not location.startswith(("//", "/\\"))


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
	frappe.flags.redirect_location = encode_target(target)
	raise frappe.Redirect(status_code)


def encode_target(target: str) -> str:
	"""`target` with the query string of the request.
	The path arrives percent-decoded: re-encode it, or a "?" in an item code starts the query string."""
	target = quote(clean_path(target), safe="/:,;=@!$&'()*+~")
	request = getattr(frappe.local, "request", None)
	query_string = frappe.safe_decode(request.query_string) if request else ""
	return f"{target}?{query_string}" if query_string else target


def clean_path(path: str) -> str:
	"""`path` with exactly one leading slash. "//host" or "/\\host" would send a redirect off-site."""
	return "/" + (path or "").strip(" ").strip("/\\")


def skip_frappe_redirects(path: str):
	"""The rules ran in localize_request. Frappe's PathResolver would match them again on the
	stripped path and send /x back to /en/x. frappe.local.cache lives for this request only."""
	key = frappe.cache.make_key("website_redirects")
	frappe.local.cache.setdefault(key, {})[path.strip("/ ") or "/"] = False


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
