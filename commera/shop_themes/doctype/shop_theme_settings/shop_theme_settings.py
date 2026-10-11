import re

import frappe
from frappe.model.document import Document

from commera.shop_themes.doctype.shop_theme.shop_theme import clear_render_theme_context

LANG = r"(?P<lang>en|ar)"

# The routes the bundled themes ship pages for.
# Seeded from after_install and after_migrate too: a fresh install marks patches applied without running them.
DEFAULT_ROUTES = [
	{"url_pattern": rf"^{LANG}$", "template_path": "pages/index.html", "requires_auth": 0},
	{
		"url_pattern": rf"^{LANG}/products$",
		"template_path": "pages/products/list.html",
		"requires_auth": 0,
	},
	{
		"url_pattern": rf"^{LANG}/products/(?P<route>.+)$",
		"template_path": "pages/products/details.html",
		"requires_auth": 0,
	},
	{"url_pattern": rf"^{LANG}/cart$", "template_path": "pages/cart/cart.html", "requires_auth": 0},
	# requires_auth 0 on purpose: the resolver's gate 403s before the controller can send a guest to the cart.
	{
		"url_pattern": rf"^{LANG}/cart/checkout$",
		"template_path": "pages/cart/checkout.html",
		"requires_auth": 0,
	},
	{
		"url_pattern": rf"^{LANG}/cart/(?!checkout$)(?P<codes>.+)$",
		"template_path": "pages/cart/permalink.html",
		"requires_auth": 0,
	},
	{
		"url_pattern": rf"^{LANG}/account/dashboard$",
		"template_path": "pages/account/dashboard.html",
		"requires_auth": 1,
	},
	{
		"url_pattern": rf"^{LANG}/account/profile$",
		"template_path": "pages/account/profile.html",
		"requires_auth": 1,
	},
	{
		"url_pattern": rf"^{LANG}/account/orders$",
		"template_path": "pages/account/orders/index.html",
		"requires_auth": 1,
	},
	# requires_auth 0 on purpose: a guest opens the private order link; the controller checks its key.
	{
		"url_pattern": rf"^{LANG}/account/orders/detail$",
		"template_path": "pages/account/orders/detail.html",
		"requires_auth": 0,
	},
	{
		"url_pattern": rf"^{LANG}/track-order$",
		"template_path": "pages/track_order.html",
		"requires_auth": 0,
	},
	# requires_auth 0 on purpose: this is the gateway return URL, so the page asks for the login itself.
	{
		"url_pattern": rf"^{LANG}/account/orders/confirmation$",
		"template_path": "pages/account/orders/confirmation.html",
		"requires_auth": 0,
	},
	{
		"url_pattern": rf"^{LANG}/account/wishlist$",
		"template_path": "pages/account/wishlist.html",
		"requires_auth": 1,
	},
	{
		"url_pattern": rf"^{LANG}/account/address$",
		"template_path": "pages/account/address.html",
		"requires_auth": 1,
	},
	# requires_auth 0 on purpose: a published content page is public, and the controller is what lets
	# an editor preview an unpublished one.
	{
		"url_pattern": rf"^{LANG}/page/(?P<route>.+)$",
		"template_path": "pages/shop_web_page.html",
		"requires_auth": 0,
	},
]

COMPILED_ROUTES_CACHE_KEY = "shop_theme_compiled_routes"


class ShopThemeSettings(Document):
	def validate(self):
		for row in self.get("routes") or []:
			try:
				re.compile(row.url_pattern)
			except re.error as error:
				frappe.throw(frappe._("Invalid regex in route {0}: {1}").format(row.url_pattern, error))

	def on_update(self):
		clear_settings_cache()


def seed_default_routes():
	"""Add any missing default route; idempotent on url_pattern so custom routes survive."""
	settings = frappe.get_single("Shop Theme Settings")
	existing_patterns = {row.url_pattern for row in settings.routes}

	missing_routes = [route for route in DEFAULT_ROUTES if route["url_pattern"] not in existing_patterns]
	if not missing_routes:
		return

	for route in missing_routes:
		settings.append("routes", route)

	settings.save(ignore_permissions=True)


def clear_settings_cache():
	frappe.cache.delete_value(COMPILED_ROUTES_CACHE_KEY)
	frappe.local.shop_theme_compiled_routes = None
	# The active theme lives on this Single, so the memoised render context is stale too.
	clear_render_theme_context()


def build_compiled_routes():
	settings = frappe.get_cached_doc("Shop Theme Settings")
	compiled = []
	for row in settings.get("routes") or []:
		try:
			pattern = re.compile(row.url_pattern)
		except re.error:
			continue
		compiled.append(
			{
				"pattern": pattern,
				"template_path": row.template_path,
				"requires_auth": bool(row.requires_auth),
			}
		)
	return {"routes": compiled, "dynamic_pages_enabled": bool(settings.dynamic_pages_enabled)}


def get_compiled_routes():
	# Memoised on frappe.local over redis too: regex compilation showed up hot per request.
	routes = getattr(frappe.local, "shop_theme_compiled_routes", None)
	if routes is None:
		routes = frappe.cache.get_value(COMPILED_ROUTES_CACHE_KEY, generator=build_compiled_routes)
		frappe.local.shop_theme_compiled_routes = routes
	return routes
