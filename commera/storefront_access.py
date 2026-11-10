import frappe
from frappe.website.utils import build_response

from commera.api.permission import has_app_permission
from commera.localization import StorefrontLanguages

SETTINGS_DOCTYPE = "Commera Settings"

# Unprefixed www pages render without the language prefix; sitemap* and llms.txt list the catalogue.
STOREFRONT_SEGMENTS = frozenset(
	{
		"",
		"index",
		"cart",
		"account",
		"storefront-cart",
		"storefront-login",
		"og-image",
		"llms.txt",
	}
)


def get_store_name() -> str:
	return (
		frappe.get_cached_doc(SETTINGS_DOCTYPE).store_name
		or frappe.get_cached_doc("Website Settings").app_name
		or ""
	)


def is_storefront_published() -> bool:
	return bool(frappe.get_cached_doc(SETTINGS_DOCTYPE).storefront_published)


def is_storefront_path(path: str) -> bool:
	segment = path.strip("/").split("/", 1)[0]
	return (
		segment in STOREFRONT_SEGMENTS
		or segment.startswith("sitemap")
		or bool(StorefrontLanguages.load().find(segment, include_unpublished=True))
	)


class PrivateStorefrontPage:
	def __init__(self, path, http_status_code=None):
		self.path = path

	def can_render(self):
		request = getattr(frappe.local, "request", None)
		path = request.path if request else self.path
		if not is_storefront_path(path) or is_storefront_published():
			return False
		return frappe.session.user == "Guest" or not has_app_permission()

	def render(self):
		website_settings = frappe.get_cached_doc("Website Settings")
		html = frappe.get_template("templates/storefront_private.html").render(
			{
				"store_name": get_store_name(),
				"logo": website_settings.banner_image,
				"favicon": website_settings.favicon,
			},
		)
		return build_response(
			self.path,
			html,
			503,
			{"Cache-Control": "no-store", "X-Robots-Tag": "noindex", "Retry-After": "86400"},
		)
