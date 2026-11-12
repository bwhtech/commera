"""OG cards for the /og-image endpoint and the admin preview: HTML pages that Frappe's Chromium
screenshots through a card-only request allowlist. Only card templates reach the renderer."""

import os
import posixpath
import re
import time
from urllib.parse import quote, unquote, urlsplit

import frappe
from frappe.utils import flt, get_files_path, get_url

from commera import seo
from commera.branding import get_brand_assets
from commera.localization import get_localization
from commera.og.chromium import get_preview_from_html
from commera.shop_themes.render import render_themed_template

# Social card spec used by Facebook/X/LinkedIn; 1.91:1 ratio.
DEFAULT_OG_WIDTH = 1200
DEFAULT_OG_HEIGHT = 630

BUNDLED_CARD_TEMPLATE = "commera/templates/og/product_card.html"
STORE_CARD_TEMPLATE = "commera/templates/og/store_card.html"
CARD_PAGE_TEMPLATE = "commera/templates/og/base.html"

# Chromium reads this site's files from disk, so the card may not load anything from another host.
CONTENT_POLICY = (
	'<meta http-equiv="Content-Security-Policy" content="'
	"default-src 'none'; img-src 'self' data:; font-src 'self' data:; style-src 'unsafe-inline'; "
	"base-uri 'none'; form-action 'none'\">"
)
DOCTYPE = re.compile(r"\A\s*<!doctype[^>]*>", re.IGNORECASE)
HTML_TAG = re.compile(r"<html[\s>]", re.IGNORECASE)


def render_card_image(html_str):
	"""The card as JPEG bytes."""
	return get_preview_from_html(
		with_content_policy(html_str), format="jpg", width=DEFAULT_OG_WIDTH, height=DEFAULT_OG_HEIGHT
	)


def render_card_for_doc(for_doctype, doc, with_price=True):
	context = context_builder_for(for_doctype)(doc, with_price=with_price)
	return render_card_image(render_card_html(resolve_template(for_doctype), context))


def render_card_html(template, context):
	"""The card page. A template that is only a fragment, as the old renderer took, gets the page around it."""
	context = {**page_context(), **context}
	# nosemgrep: frappe-ssti  # template is a bundled card or an admin-authored OG Image Template
	html_str = render_themed_template(template, context)
	if HTML_TAG.search(html_str):
		return html_str
	return render_themed_template(CARD_PAGE_TEMPLATE, {**context, "fragment": html_str})


def build_store_card_html():
	logo_url = card_image_url(get_brand_assets().logo)
	context = {
		"store_name": seo.get_store_name(),
		"tagline": seo.get_store_description() or seo.default_store_description(),
		"site_host": urlsplit(get_url()).hostname or "",
		"logo_url": logo_url,
		# The old renderer's name; theme templates may still use it.
		"logo_data_uri": logo_url,
	}
	return render_card_html(STORE_CARD_TEMPLATE, context)


def build_variant_card_context(variant_doc, with_price=True):
	"""`with_price` False drops the price: a secondary market's card would show the store price."""
	from commera.product_detail import get_product_detail

	detail = get_product_detail(variant_doc.route)
	brand = ""
	price = ""
	photo_url = None
	if detail:
		brand = detail["product"].brand or ""
		amount = detail["sale_price"] or detail["default_price"]
		if amount and with_price:
			price = f"{seo.get_site_currency()} {flt(amount):.2f}"
		images = detail["images"]
		if images:
			photo_url = card_image_url(images[0])

	return {
		"store_name": seo.get_store_name(),
		"display_name": get_card_title(variant_doc),
		"brand": brand,
		"price": price,
		"photo_url": photo_url,
		# The old renderer's name; OG Image Templates may still use it.
		"photo_data_uri": photo_url,
		# DocType templates address the source document as `doc`.
		"doc": variant_doc,
	}


def get_card_title(variant_doc) -> str:
	"""The product's title in the request language and market, as its page shows it."""
	from commera.sdk.catalog import translate_products

	return (
		translate_products([variant_doc])[0]["display_name"] or variant_doc.display_name or variant_doc.name
	)


def get_variant_card_version(variant_doc) -> str:
	"""What a product card's cache key must change with: the record, and its translated text."""
	localization = get_localization()
	market = localization.market.handle if localization.market else ""
	text = [localization.language.code, market, seo.get_store_name(), get_card_title(variant_doc)]
	return frappe.as_json([str(variant_doc.modified), *text])


OG_CONTEXT_BUILDERS = {
	"Style Attribute Variant": build_variant_card_context,
}


def context_builder_for(for_doctype):
	builder = OG_CONTEXT_BUILDERS.get(for_doctype)
	if not builder:
		frappe.throw(f"No OG card context builder registered for DocType {for_doctype}")
	return builder


def resolve_template(for_doctype):
	"""Admin-edited Jinja string if enabled, else the bundled card path (both accepted by render_template)."""
	template_html = frappe.db.get_value(
		"OG Image Template",
		{"for_doctype": for_doctype, "enabled": 1},
		"template_html",
	)
	return template_html or BUNDLED_CARD_TEMPLATE


def variant_primary_image_url(variant_name):
	return frappe.db.get_value(
		"Website Slideshow Item",
		{"parent": variant_name, "parenttype": "Style Attribute Variant"},
		"image",
		order_by="idx asc",
	)


def card_image_url(image_url):
	"""The URL of a public site file or asset that exists, else None: never a remote or private image."""
	parts = urlsplit(image_url or "")
	url_path = unquote(parts.path)
	# A `..` or `//` would let Chromium leave /files/ after this check.
	if parts.scheme or parts.netloc or posixpath.normpath(url_path) != url_path:
		return None

	if url_path.startswith("/files/"):
		disk_path = get_files_path(url_path.removeprefix("/files/"), is_private=False)
	elif url_path.startswith("/assets/"):
		disk_path = os.path.join(frappe.local.sites_path, url_path.lstrip("/"))
	else:
		return None
	return quote(url_path) if os.path.isfile(disk_path) else None


def page_context():
	language = get_localization().language
	return {"lang": language.code, "dir": language.direction}


def with_content_policy(html_str):
	"""Put the content policy first in the page, after the doctype, whatever the template wrote."""
	doctype = DOCTYPE.match(html_str)
	at = doctype.end() if doctype else 0
	return html_str[:at] + CONTENT_POLICY + html_str[at:]


# Keyed on route+modified, so every edit strands the previous card; bound the directory.
CARD_CACHE_MAX_AGE_DAYS = 30
CARD_SUFFIXES = (".jpg", ".png")


def clear_old_cards(days=CARD_CACHE_MAX_AGE_DAYS):
	cache_dir = os.path.join(get_files_path(is_private=False), "og-cache")
	if not os.path.isdir(cache_dir):
		return

	cutoff = time.time() - (days * 86400)
	for filename in os.listdir(cache_dir):
		# A .tmp- file is a write that did not finish.
		if not filename.endswith(CARD_SUFFIXES) and ".tmp-" not in filename:
			continue
		path = os.path.join(cache_dir, filename)
		if os.path.getmtime(path) < cutoff:
			os.remove(path)
