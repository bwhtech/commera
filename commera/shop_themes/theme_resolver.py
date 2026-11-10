import importlib.util
import os
from urllib.parse import quote

import frappe
from frappe.utils.data import cint
from frappe.utils.jinja import get_jenv
from frappe.website.doctype.website_settings.website_settings import get_website_settings
from frappe.website.utils import build_response
from jinja2 import BaseLoader, BytecodeCache, TemplateNotFound
from jinja2.utils import LRUCache

import commera.sdk
from commera.localization import get_localization, get_request_path, get_route_path
from commera.localization.routing import localize_path
from commera.shop_themes.doctype.shop_theme.shop_theme import (
	get_render_theme_context,
	is_within_directory,
)
from commera.shop_themes.doctype.shop_theme_settings.shop_theme_settings import get_compiled_routes
from commera.shop_themes.jinja_helpers import get_shop_theme_settings
from commera.shop_themes.route_patterns import has_language_group
from commera.utils import get_currency_symbols, get_store_currency

# page_renderer runs before every built-in renderer: a segment missing here is a route hijack, not a 404.
RESERVED_PATH_SEGMENTS = frozenset(
	{
		"api",
		"app",
		"assets",
		"backups",
		"desk",
		"files",
		"login",
		"method",
		"og-image",
		"private",
		"robots.txt",
		"sitemap.xml",
		"llms.txt",
		"socket.io",
		"update-password",
		"website_script.js",
	}
)

# Bare template names resolve from a theme only under this prefix: otherwise a theme could shadow
# templates/includes/header.html and silently disconnect the menu manager and footer editor.
THEME_OVERRIDABLE_PREFIX = "components/"

DEFAULT_APP_NAME = "Commera"

NOT_FOUND_TEMPLATE = "pages/404.html"
LOGIN_TEMPLATE = "pages/account/login.html"


def find_theme_file(theme_dirs, relative_path):
	for theme_dir in theme_dirs:
		candidate = os.path.join(theme_dir, relative_path)
		if is_within_directory(theme_dir, candidate) and os.path.isfile(candidate):
			return candidate
	return None


page_controller_modules = {}


def load_page_controller(theme_dirs, template_relative_path):
	controller_relative_path = f"{os.path.splitext(template_relative_path)[0]}.py"
	controller_path = find_theme_file(theme_dirs, controller_relative_path)
	if not controller_path:
		return None

	modified_time = os.path.getmtime(controller_path)
	cached = page_controller_modules.get(controller_path)
	if cached and cached[0] == modified_time:
		return cached[1]

	module_name = build_controller_module_name(theme_dirs, controller_path, controller_relative_path)
	spec = importlib.util.spec_from_file_location(module_name, controller_path)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	page_controller_modules[controller_path] = (modified_time, module)
	return module


def build_controller_module_name(theme_dirs, controller_path, relative_path):
	theme_slug = ""
	for theme_dir in theme_dirs:
		if os.path.join(theme_dir, relative_path) == controller_path:
			theme_slug = os.path.basename(theme_dir.rstrip(os.sep))
			break

	page_slug = os.path.splitext(relative_path)[0]
	for separator in (os.sep, "/", "-", "."):
		page_slug = page_slug.replace(separator, "_")

	return f"commera.shop_themes.theme_pages.{theme_slug}.{page_slug}"


def run_page_controller(theme_dirs, template_relative_path, context):
	module = load_page_controller(theme_dirs, template_relative_path)
	if not module or not hasattr(module, "get_context"):
		return

	data = module.get_context(context)
	if data:
		context.update(data)


class ThemePageRenderer:
	def __init__(self, path, http_status_code=None):
		self.path = path
		self.http_status_code = http_status_code
		self.theme_dirs = None
		self.template_path = None
		self.match = None
		self.requires_auth = False

	def can_render(self):
		page = find_theme_page(self.get_request_path(), get_localization().language.code)
		if not page:
			return False

		self.theme_dirs, self.template_path, self.requires_auth, self.match = page
		return True

	def get_request_path(self):
		# The path without its language prefix, not what website_route_rules rewrote it to.
		# Only a localized request loses its prefix: /ar/private/x stays outside the storefront.
		if getattr(frappe.local, "request", None):
			return get_route_path().strip("/")
		localized = localize_path(self.path)
		return (localized.route_path if localized else self.path).strip("/")

	def render(self):
		if self.requires_auth and frappe.session.user == "Guest":
			self.redirect_guest_to_login()

		context = build_base_context(self.match)
		try:
			run_page_controller(self.theme_dirs, self.template_path, context)
		except (frappe.PageDoesNotExistError, frappe.DoesNotExistError):
			if not find_theme_file(self.theme_dirs, NOT_FOUND_TEMPLATE):
				raise
			return self.render_not_found()
		html = self.render_with_theme_loader(context)
		return build_response(self.path, html, self.http_status_code or 200)

	def redirect_guest_to_login(self):
		"""Send a guest to the theme's own login page, which returns them here after signing in."""
		if not find_theme_file(self.theme_dirs, LOGIN_TEMPLATE):
			raise frappe.PermissionError
		return_path = quote(get_request_path() or "/" + self.path.strip("/"), safe="/")
		login_path = f"{get_localization().root_prefix}/account/login"
		frappe.flags.redirect_location = f"{login_path}?redirect-to={return_path}"
		raise frappe.Redirect(302)

	def render_not_found(self):
		html = self.get_not_found_html()
		return build_response(self.path, html, 404, {"Cache-Control": "no-store"})

	def get_not_found_html(self):
		frappe.clear_last_message()
		self.template_path = NOT_FOUND_TEMPLATE
		context = build_base_context(None)
		run_page_controller(self.theme_dirs, self.template_path, context)
		return self.render_with_theme_loader(context)

	def render_with_theme_loader(self, context):
		theme_env = get_theme_environment(get_jenv(), self.theme_dirs)
		template = theme_env.get_template(f"theme://{self.template_path}")
		return template.render(context)


def find_theme_page(request_path, language_code=None):
	"""(theme dirs, template path, requires_auth, match) of the active theme's page, or None."""
	theme_context = get_render_theme_context()
	if not theme_context["theme_name"] or not theme_context["dirs"]:
		return None

	settings = get_compiled_routes()
	legacy_path = f"{language_code.lower()}/{request_path}".rstrip("/") if language_code else None
	matched_route, match = match_route(settings["routes"], request_path, legacy_path)
	if matched_route:
		template_path, requires_auth = matched_route["template_path"], matched_route["requires_auth"]
	elif is_dynamic_page(settings, request_path):
		template_path, requires_auth = f"pages/{request_path}.html", False
	else:
		return None

	# No fallback template: a theme that lacks this page declines and stock frappe routing serves it.
	if not find_theme_file(theme_context["dirs"], template_path):
		return None
	return theme_context["dirs"], template_path, requires_auth, match


def match_route(routes, request_path, legacy_path=None):
	"""`legacy_path` is the path as it was under /<lang>/. A route that the language patch kept
	with its (?P<lang>…) group matches it, so it still wins in its old place."""
	for route in routes:
		is_legacy = legacy_path is not None and has_language_group(route["pattern"].pattern)
		match = route["pattern"].match(legacy_path if is_legacy else request_path)
		if match:
			return route, match
	return None, None


def is_dynamic_page(settings, request_path):
	if not settings["dynamic_pages_enabled"] or not request_path:
		return False

	segments = request_path.split("/")

	# werkzeug percent-decodes request.path, so %2e%2e%2f arrives here as "..".
	if ".." in segments:
		return False

	return segments[0] not in RESERVED_PATH_SEGMENTS


class ThemeFallbackLoader(BaseLoader):
	def __init__(self, theme_dirs, fallback_loader):
		self.theme_dirs = tuple(theme_dirs)
		self.fallback_loader = fallback_loader

	def get_source(self, environment, template):
		if template.startswith("theme://"):
			relative_path = template[len("theme://") :]
			full_path = find_theme_file(self.theme_dirs, relative_path)
			if full_path:
				return read_template_source(full_path)
			raise TemplateNotFound(template)

		if template.startswith(THEME_OVERRIDABLE_PREFIX):
			full_path = find_theme_file(self.theme_dirs, template)
			if full_path:
				return read_template_source(full_path)

		return self.fallback_loader.get_source(environment, template)


def read_template_source(full_path):
	modified_time = os.path.getmtime(full_path)
	# nosemgrep: frappe-semgrep-rules.rules.security.frappe-security-file-traversal
	with open(full_path) as source_file:
		source = source_file.read()
	return (
		source,
		full_path,
		lambda path=full_path, modified=modified_time: os.path.getmtime(path) == modified,
	)


class ThemeBytecodeCache(BytecodeCache):
	"""Shares compiled code across requests, never Template objects: jinja memoises a context-less
	`{% import %}` module on the Template, freezing the first request's lang, user and csrf token."""

	def __init__(self):
		self.buckets = LRUCache(200)

	def load_bytecode(self, bucket):
		cached = self.buckets.get(bucket.key)
		if cached and cached[0] == bucket.checksum:
			bucket.code = cached[1]

	def dump_bytecode(self, bucket):
		self.buckets[bucket.key] = (bucket.checksum, bucket.code)


theme_bytecode_caches = {}


def get_theme_bytecode_cache():
	# Keyed per site: theme dirs are bench-wide paths, so keying on those alone shares one cache.
	site = getattr(frappe.local, "site", None)
	bytecode_cache = theme_bytecode_caches.get(site)
	if bytecode_cache is None:
		bytecode_cache = ThemeBytecodeCache()
		theme_bytecode_caches[site] = bytecode_cache
	return bytecode_cache


def get_theme_environment(jenv, theme_dirs):
	# Built fresh per request, never cached: a jinja overlay holds a reference to jenv.globals, which
	# carries THIS request's user, form_dict, lang and csrf token.
	theme_env = jenv.overlay(loader=ThemeFallbackLoader(theme_dirs, jenv.loader))
	theme_env.auto_reload = bool(frappe.conf.get("developer_mode") or frappe._dev_server)
	theme_env.bytecode_cache = get_theme_bytecode_cache()
	return theme_env


def build_base_context(match):
	localization = get_localization()
	context = frappe._dict(is_rtl=localization.language.direction == "rtl", localization=localization)

	if match:
		apply_route_groups(match, context)

	apply_website_settings(context)
	context.theme = get_shop_theme_settings()
	context.commera_header_content = frappe.render_template(  # nosemgrep: frappe-ssti
		"templates/includes/commera-header-content.html",
		{
			"csrf_token": frappe.session.data.csrf_token,
			"store_currency": get_store_currency(),
			"currency_symbols": get_currency_symbols(),
			"language": localization.language.code,
			"localization": localization.as_dict(),
			"webmcp": bool(
				cint(frappe.get_cached_value("Commera Settings", "Commera Settings", "enable_webmcp"))
			),
		},
	)
	context.commera = commera.sdk
	apply_website_context_hooks(context)

	return context


def apply_website_settings(context):
	context.app_name = DEFAULT_APP_NAME
	context.app_logo = None
	context.boot = {}

	try:
		# Also fills context.boot; never call get_boot_data() on top of this.
		context.update(get_website_settings())

		# get_website_settings() leaves out the branding fields a theme renders the brand from.
		settings = frappe.client_cache.get_doc("Website Settings")
		context.app_name = settings.app_name or DEFAULT_APP_NAME
		context.app_logo = settings.app_logo
	except frappe.DoesNotExistError:
		# Only missing mid-install; a broader except wrote an Error Log row per anonymous page view.
		pass


def apply_route_groups(match, context):
	groups = match.groupdict() or {}
	if not groups:
		return

	# Merged into form_dict too, so a www controller reading form_dict.get("route") still works.
	context.update(groups)
	frappe.local.form_dict.update(groups)


def apply_website_context_hooks(context):
	for hook_method in frappe.get_hooks("update_website_context"):
		values = frappe.get_attr(hook_method)(context)
		if values:
			context.update(values)


def get_theme_not_found_html(path):
	"""The active theme's 404 page for `path`, or None when no theme is active or it has no 404 page."""
	theme_context = get_render_theme_context()
	if not theme_context["theme_name"] or not find_theme_file(theme_context["dirs"], NOT_FOUND_TEMPLATE):
		return None
	renderer = ThemePageRenderer(path)
	renderer.theme_dirs = theme_context["dirs"]
	return renderer.get_not_found_html()
