import re

import frappe

from commera import seo
from commera.localization import get_localization

# Cart/account/login render per-user content and must never be indexed.
UTILITY_PATH_PATTERN = re.compile(r"^/(?:en|ar)/(cart|account|login)(?:/|$)")

UTILITY_PAGE_NAMES = {"cart": "Cart", "account": "My Account", "login": "Login"}


def update_website_context(context):
	context.localization = get_localization()

	request = getattr(frappe.local, "request", None)
	request_path = request.path if request else ""

	match = UTILITY_PATH_PATTERN.match(request_path)
	if not match:
		return

	context.no_cache = 1
	context.seo = seo.build_page_seo({"noindex": 1}, display_name=UTILITY_PAGE_NAMES[match.group(1)])
	context.json_ld = []
