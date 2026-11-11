import frappe
from frappe.website.utils import build_response

from commera.api.permission import has_app_permission
from commera.builder_themes.pages import is_builder_theme_path
from commera.localization import StorefrontLanguages, get_request_path, strip_language_prefix
from commera.localization.routing import is_page_path

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


def is_storefront_hidden() -> bool:
	"""The storefront is unpublished and this user may not see it yet."""
	return not is_storefront_published() and (frappe.session.user == "Guest" or not has_app_permission())


def is_storefront_path(path: str) -> bool:
	"""A language-prefixed page path, a storefront page or a page of the active theme.
	The theme test takes the path as is: the renderer keeps the prefix of /ar/private/x too."""
	path = "/" + path.strip("/")
	language, rest = strip_language_prefix(path, include_unpublished=True)
	if language and is_page_path(rest):
		return True
	segment = path.strip("/").split("/", 1)[0]
	return segment in STOREFRONT_SEGMENTS or segment.startswith("sitemap") or has_theme_page(path)


def has_theme_page(path: str) -> bool:
	"""A page of the active theme at `path` in the default language, which has no prefix."""
	from commera.shop_themes.theme_resolver import find_theme_page

	return find_theme_page(path.strip("/"), StorefrontLanguages.load().default.code) is not None


class PrivateStorefrontPage:
	def __init__(self, path, http_status_code=None):
		self.path = path

	def can_render(self):
		path = get_request_path() or self.path
		return (is_storefront_path(path) or is_builder_theme_path(path)) and is_storefront_hidden()

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
