import os

import frappe
from frappe.utils.jinja import get_jenv
from frappe.utils.jinja_globals import is_rtl
from frappe.website.doctype.website_settings.website_settings import get_website_settings
from frappe.website.utils import build_response
from jinja2 import BaseLoader, BytecodeCache, TemplateNotFound
from jinja2.utils import LRUCache

from commera.shop_themes.doctype.shop_theme.shop_theme import get_render_theme_context
from commera.shop_themes.doctype.shop_theme_settings.shop_theme_settings import get_compiled_routes
from commera.shop_themes.section_render import get_theme_settings
from commera.shop_themes.theme_files import DYNAMIC_PAGE_LANG_PREFIXES, find_theme_file, load_theme_module

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


def load_page_controller(theme_dirs, template_relative_path):
	controller_relative_path = f"{os.path.splitext(template_relative_path)[0]}.py"
	return load_theme_module(theme_dirs, controller_relative_path, "theme_pages")


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
		theme_context = get_render_theme_context()
		if not theme_context["theme_name"] or not theme_context["dirs"]:
			return False

		request_path = self.get_request_path()
		settings = get_compiled_routes()

		matched_route, match = match_route(settings["routes"], request_path)
		if matched_route:
			template_path = matched_route["template_path"]
			requires_auth = matched_route["requires_auth"]
		elif is_dynamic_page(settings, request_path):
			template_path = f"pages/{request_path}.html"
			requires_auth = False
		else:
			return False

		# No fallback template: a theme that lacks this page declines and stock frappe routing serves it.
		if not find_theme_file(theme_context["dirs"], template_path):
			return False

		self.theme_dirs = theme_context["dirs"]
		self.template_path = template_path
		self.match = match
		self.requires_auth = requires_auth
		return True

	def get_request_path(self):
		# The RAW request path, not what website_route_rules rewrote it to, so a themed route bypasses them.
		request = getattr(frappe.local, "request", None)
		if request:
			return request.path.strip("/")
		return self.path.strip("/")

	def render(self):
		if self.requires_auth and frappe.session.user == "Guest":
			raise frappe.PermissionError

		context = build_base_context(self.match)
		run_page_controller(self.theme_dirs, self.template_path, context)
		html = self.render_with_theme_loader(context)
		return build_response(self.path, html, self.http_status_code or 200)

	def render_with_theme_loader(self, context):
		theme_env = get_theme_environment(get_jenv(), self.theme_dirs)
		template = theme_env.get_template(f"theme://{self.template_path}")
		return template.render(context)


def match_route(routes, request_path):
	for route in routes:
		match = route["pattern"].match(request_path)
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

	first_segment = segments[0]
	if first_segment in RESERVED_PATH_SEGMENTS:
		return False

	return first_segment in DYNAMIC_PAGE_LANG_PREFIXES


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
	context = frappe._dict(is_rtl=is_rtl(), theme_settings=get_theme_settings(get_render_theme_context()))

	if match:
		apply_route_groups(match, context)

	apply_website_settings(context)
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
