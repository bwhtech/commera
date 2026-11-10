"""SEO fallbacks registered in `hooks.jinja`: the Jinja sandbox wraps docs as SafeDoc, whose methods
silently return None, so controller methods are unreachable from a template."""

import frappe

from commera import seo


def seo_page_meta():
	# A broken Commera Settings doc must never 500 the storefront over meta tags.
	try:
		return seo.default_seo()
	except Exception:
		frappe.log_error(title="SEO default meta build failed")
		return {}


def seo_org_jsonld():
	try:
		return seo.org_website_json_ld()
	except Exception:
		frappe.log_error(title="SEO organization JSON-LD build failed")
		return []


def seo_og_locales():
	try:
		return seo.get_og_locales()
	except Exception:
		frappe.log_error(title="SEO og:locale build failed")
		return {}
