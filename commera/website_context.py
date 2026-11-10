import re

from commera import seo
from commera.localization import get_localization, get_request_path, strip_language_prefix

# Cart/account/login render per-user content and must never be indexed. Matched without the language prefix.
UTILITY_PATH_PATTERN = re.compile(r"^/(cart|account|login)(?:/|$)")

UTILITY_PAGE_NAMES = {"cart": "Cart", "account": "My Account", "login": "Login"}


def update_website_context(context):
	context.localization = get_localization()

	match = match_utility_path(get_request_path())
	if not match:
		return

	context.no_cache = 1
	context.seo = seo.build_page_seo({"noindex": 1}, display_name=UTILITY_PAGE_NAMES[match.group(1)])
	context.json_ld = []


def match_utility_path(path):
	_language, rest = strip_language_prefix(path, include_unpublished=True)
	return UTILITY_PATH_PATTERN.match(rest)
