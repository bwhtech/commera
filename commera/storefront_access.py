import frappe
from frappe.website.utils import build_response

from commera.api.permission import has_app_permission

SETTINGS_DOCTYPE = "Commera Settings"
PRIVATE_TEMPLATE = "templates/storefront_private.html"

# The storefront's own pages: the language-prefixed routes, plus the unprefixed cart permalink.
# Login, the dashboard, Desk, files and the API are left alone, so staff can still sign in.
STOREFRONT_SEGMENTS = frozenset({"", "en", "ar", "cart"})


def is_storefront_published() -> bool:
	return bool(frappe.get_cached_doc(SETTINGS_DOCTYPE).storefront_published)


def is_storefront_path(path: str) -> bool:
	return path.strip("/").split("/", 1)[0] in STOREFRONT_SEGMENTS


class PrivateStorefrontPage:
	"""Answers every storefront page with a coming-soon page while the store is private.

	Listed first in `page_renderer`, so it runs before the theme engine and Frappe's own renderers.
	"""

	def __init__(self, path, http_status_code=None):
		self.path = path

	def can_render(self):
		request = getattr(frappe.local, "request", None)
		path = request.path if request else self.path
		if not is_storefront_path(path) or is_storefront_published():
			return False
		return frappe.session.user == "Guest" or not has_app_permission()

	def render(self):
		settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
		website_settings = frappe.get_cached_doc("Website Settings")
		html = frappe.render_template(
			PRIVATE_TEMPLATE,
			{
				"store_name": settings.store_name or website_settings.app_name or "",
				"logo": website_settings.banner_image,
				"favicon": website_settings.favicon,
			},
		)
		# 503 tells crawlers the page is coming back, so nothing is indexed as the store's content.
		return build_response(
			self.path,
			html,
			503,
			{"Cache-Control": "no-store", "X-Robots-Tag": "noindex", "Retry-After": "86400"},
		)
