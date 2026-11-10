import frappe
from frappe.website.utils import build_response

from commera.api.permission import has_app_permission
from commera.localization import get_request_path, strip_language_prefix

SETTINGS_DOCTYPE = "Commera Settings"

# First segments of the storefront pages after the language prefix; sitemap* and llms.txt list the catalogue.
STOREFRONT_SEGMENTS = frozenset(
	{
		"",
		"index",
		"products",
		"cart",
		"account",
		"page",
		"track-order",
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
	"""A language-prefixed path, a storefront page or a page of the active theme."""
	language, rest = strip_language_prefix("/" + path.strip("/"), include_unpublished=True)
	segment = rest.strip("/").split("/", 1)[0]
	return (
		bool(language)
		or segment in STOREFRONT_SEGMENTS
		or segment.startswith("sitemap")
		or has_theme_page(rest)
	)


def has_theme_page(path: str) -> bool:
	from commera.shop_themes.theme_resolver import find_theme_page

	return find_theme_page(path.strip("/")) is not None


class PrivateStorefrontPage:
	def __init__(self, path, http_status_code=None):
		self.path = path

	def can_render(self):
		path = get_request_path() or self.path
		if is_storefront_published() or not is_storefront_path(path):
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
