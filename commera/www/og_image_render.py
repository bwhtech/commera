"""Serves /og-image/<route>.png over og.generator."""

import hashlib
import os

import frappe
from frappe.utils import get_files_path

from commera.branding import get_brand_assets
from commera.localization import get_localization
from commera.og.generator import (
	DEFAULT_OG_HEIGHT,
	DEFAULT_OG_WIDTH,
	build_store_card_html,
	get_variant_card_version,
	render_card_for_doc,
	render_og_png,
	variant_primary_image_url,
)

# Bump whenever fonts, layout or text rendering change.
RENDERER_VERSION = 3

CACHE_SUBDIR = "og-cache"
STORE_CARD_ROUTE = "store"
# `?price=none` asks for a card without the store price, for pages of a secondary market.
NO_PRICE = "none"


def get_context(context):
	route = (frappe.form_dict.get("route") or "").removesuffix(".png")
	if not route:
		raise frappe.PageDoesNotExistError()

	try:
		if route == STORE_CARD_ROUTE:
			serve_store_card()
		serve_og_image(route, with_price=frappe.form_dict.get("price") != NO_PRICE)
	except frappe.Redirect:
		raise
	except frappe.DoesNotExistError:
		raise frappe.PageDoesNotExistError()
	except Exception:
		# Never break the crawler over a card render; fall back to the store logo or product photo.
		frappe.log_error("og_image_render failed")
		fallback = get_brand_assets().logo if route == STORE_CARD_ROUTE else product_photo_url(route)
		if fallback:
			frappe.local.flags.redirect_location = fallback
			raise frappe.Redirect
		raise frappe.PageDoesNotExistError()

	return context


def serve_og_image(route, with_price=True):
	variant = frappe.db.get_value(
		"Style Attribute Variant",
		{"route": route},
		["name", "modified", "is_published"],
		as_dict=True,
	)
	if not variant or not variant.is_published:
		raise frappe.DoesNotExistError()

	variant_doc = frappe.get_cached_doc("Style Attribute Variant", variant.name)
	# /en-ae/og-image/<route>.png renders the Gulf market text in English.
	card = route if with_price else f"{route}?price={NO_PRICE}"
	cache_path = cache_file_path(card, get_variant_card_version(variant_doc))
	if not os.path.exists(cache_path):
		png_bytes = render_card_for_doc("Style Attribute Variant", variant_doc, with_price=with_price)
		write_cache(cache_path, png_bytes)

	redirect_to_cached_card(cache_path)


def serve_store_card():
	html_str = build_store_card_html()
	# Keyed on the markup, so a new name, tagline or logo yields a fresh card. A right-to-left card
	# mirrors the same markup.
	direction = get_localization().language.direction
	cache_path = cache_file_path(STORE_CARD_ROUTE, frappe.as_json([direction, html_str]))
	if not os.path.exists(cache_path):
		write_cache(cache_path, render_og_png(html_str, DEFAULT_OG_WIDTH, DEFAULT_OG_HEIGHT))

	redirect_to_cached_card(cache_path)


def redirect_to_cached_card(cache_path):
	# www TemplatePage discards a streamed frappe.local.response, so serve the cached card via a redirect.
	public_root = get_files_path(is_private=False)
	file_url = "/files/" + os.path.relpath(cache_path, public_root).replace(os.sep, "/")
	frappe.local.flags.redirect_location = file_url
	raise frappe.Redirect


def product_photo_url(route):
	variant_name = frappe.db.get_value("Style Attribute Variant", {"route": route}, "name")
	if not variant_name:
		return None
	return variant_primary_image_url(variant_name)


def cache_file_path(route, version):
	cache_dir = os.path.join(get_files_path(is_private=False), CACHE_SUBDIR)
	os.makedirs(cache_dir, exist_ok=True)
	# NOT frappe.generate_hash: it ignores its input and returns a random token, which defeats the cache.
	key = hashlib.md5(f"{RENDERER_VERSION}-{route}-{version}".encode(), usedforsecurity=False).hexdigest()[
		:16
	]
	return os.path.join(cache_dir, f"{key}.png")


def write_cache(cache_path, png_bytes):
	# nosemgrep: frappe-security-file-traversal  # cache filename is an md5 hexdigest, not user-controlled
	with open(cache_path, "wb") as cache_file:
		cache_file.write(png_bytes)
