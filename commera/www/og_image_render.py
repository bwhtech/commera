"""Serves /og-image/<route>.jpg over og.generator."""

import glob
import hashlib
import os
import uuid

import frappe
from frappe.utils import get_files_path

from commera import seo
from commera.branding import get_brand_assets
from commera.localization import get_localization
from commera.og.generator import (
	build_store_card_html,
	get_variant_card_version,
	render_card_for_doc,
	render_card_image,
	variant_primary_image_url,
)

# Bump whenever fonts, layout or text rendering change.
RENDERER_VERSION = 4

CACHE_SUBDIR = "og-cache"
STORE_CARD_ROUTE = "store"
# `?price=none` asks for a card without the store price, for pages of a secondary market.
NO_PRICE = "none"

# Exceeds the 180-second CDP render deadline and cold Chromium startup.
LOCK_TTL = 300
# A failed render is not tried again for this long, so crawlers do not restart Chromium on every hit.
FAILURE_TTL = 600
RETRY_AFTER = 10


class CardBusy(Exception):
	"""Another request is rendering this card."""

	http_status_code = 503


class CardFailed(Exception):
	"""This card failed to render a short time ago."""


def get_context(context):
	requested = frappe.form_dict.get("route") or ""
	if requested.endswith(".png"):
		redirect_to_jpg(requested.removesuffix(".png"))

	route = requested.removesuffix(".jpg")
	if not route:
		raise frappe.PageDoesNotExistError()

	try:
		if route == STORE_CARD_ROUTE:
			serve_store_card()
		serve_og_image(route, with_price=frappe.form_dict.get("price") != NO_PRICE)
	except frappe.Redirect:
		raise
	except CardBusy:
		frappe.local.response_headers["Retry-After"] = str(RETRY_AFTER)
		raise
	except frappe.DoesNotExistError:
		raise frappe.PageDoesNotExistError()
	except Exception as error:
		# Never break the crawler over a card render; fall back to the store logo or product photo.
		if not isinstance(error, CardFailed):
			frappe.log_error("og_image_render failed")
		fallback = get_brand_assets().logo if route == STORE_CARD_ROUTE else product_photo_url(route)
		if fallback:
			frappe.local.flags.redirect_location = fallback
			raise frappe.Redirect(302)
		raise frappe.PageDoesNotExistError()

	return context


def redirect_to_jpg(route):
	"""Cards were PNG before. Crawlers that kept an old URL get the JPEG card."""
	url = seo.get_default_og_image() if route == STORE_CARD_ROUTE else seo.get_product_og_image(route)
	if frappe.form_dict.get("price") == NO_PRICE:
		url = f"{url}?price={NO_PRICE}"
	frappe.local.flags.redirect_location = url
	raise frappe.Redirect(301)


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
	# /en-ae/og-image/<route>.jpg renders the Gulf market text in English.
	card = route if with_price else f"{route}?price={NO_PRICE}"
	cache_path = cache_file_path(card, get_variant_card_version(variant_doc))
	if not os.path.exists(cache_path):
		render_once(
			cache_path,
			lambda: render_card_for_doc("Style Attribute Variant", variant_doc, with_price=with_price),
			# A locking read sees committed changes even in a REPEATABLE READ request snapshot.
			lambda: cache_file_path(
				card,
				get_variant_card_version(
					frappe.get_doc("Style Attribute Variant", variant.name, for_update=True)
				),
			),
		)

	redirect_to_cached_card(cache_path)


def serve_store_card():
	html_str = build_store_card_html()
	# Keyed on the markup, so a new name, tagline, logo or language yields a fresh card.
	cache_path = cache_file_path(STORE_CARD_ROUTE, html_str)
	if not os.path.exists(cache_path):
		render_once(
			cache_path,
			lambda: render_card_image(html_str),
			lambda: cache_file_path(STORE_CARD_ROUTE, build_store_card_html()),
		)

	redirect_to_cached_card(cache_path)


def render_once(cache_path, render, current_path=None):
	"""Render a card at most once at a time. A request that finds the card being rendered gets a 503."""
	name = os.path.basename(cache_path)
	failure_key = f"commera_og_failed:{name}"
	lock_key = f"commera_og_lock:{name.split('-', 1)[0]}"
	token = uuid.uuid4().hex
	redis_key = frappe.cache.make_key(lock_key)
	if frappe.cache.get_value(failure_key):
		raise CardFailed

	# set_value cannot set only-if-absent: the lock needs Redis SET NX.
	# nosemgrep: frappe-semgrep-rules.rules.frappe-cache-breaks-multitenancy
	if not frappe.cache.set(redis_key, token, nx=True, ex=LOCK_TTL):
		raise CardBusy

	try:
		# Another request may have written it between our check and the lock.
		if not os.path.exists(cache_path):
			older = card_versions(cache_path)
			image = render()
			# Redis locks contain raw tokens, not pickled cache values.
			if not owns_lock(redis_key, token) or (current_path and current_path() != cache_path):
				raise CardBusy
			write_cache(cache_path, image)
			remove_older_cards(cache_path, older)
	except CardBusy:
		raise
	except Exception as error:
		frappe.cache.set_value(failure_key, 1, expires_in_sec=FAILURE_TTL)
		frappe.log_error("OG card render failed")
		raise CardFailed from error
	finally:
		release_lock(redis_key, token)


def redirect_to_cached_card(cache_path):
	# www TemplatePage discards a streamed frappe.local.response, so serve the cached card via a redirect.
	public_root = get_files_path(is_private=False)
	file_url = "/files/" + os.path.relpath(cache_path, public_root).replace(os.sep, "/")
	frappe.local.flags.redirect_location = file_url
	# Not 301: the file is removed when the card changes.
	raise frappe.Redirect(302)


def product_photo_url(route):
	variant_name = frappe.db.get_value("Style Attribute Variant", {"route": route}, "name")
	if not variant_name:
		return None
	return variant_primary_image_url(variant_name)


def cache_file_path(card, version):
	"""<card>-<version>.jpg. The card part names one card in one language and market."""
	cache_dir = os.path.join(get_files_path(is_private=False), CACHE_SUBDIR)
	os.makedirs(cache_dir, exist_ok=True)
	localization = get_localization()
	market = localization.market.handle if localization.market else ""
	card_key = digest(frappe.as_json([card, localization.language.code, market]))
	return os.path.join(cache_dir, f"{card_key}-{digest(f'{RENDERER_VERSION}-{version}')}.jpg")


def write_cache(cache_path, image_bytes):
	"""Write through a temp file, so a reader never sees half an image."""
	temp_path = f"{cache_path}.tmp-{frappe.generate_hash(length=8)}"
	# nosemgrep: frappe-security-file-traversal  # cache filename is an md5 hexdigest, not user-controlled
	with open(temp_path, "wb") as cache_file:
		cache_file.write(image_bytes)
	os.replace(temp_path, cache_path)


def card_versions(cache_path):
	card_key = os.path.basename(cache_path).split("-", 1)[0]
	return glob.glob(os.path.join(os.path.dirname(cache_path), f"{card_key}-*.jpg"))


def owns_lock(key, token):
	# nosemgrep: frappe-semgrep-rules.rules.frappe-cache-breaks-multitenancy
	return bool(frappe.cache.eval("return redis.call('get', KEYS[1]) == ARGV[1]", 1, key, token))


def release_lock(key, token):
	# Compare and delete atomically: an expired holder must not unlock its successor.
	# nosemgrep: frappe-semgrep-rules.rules.frappe-cache-breaks-multitenancy
	frappe.cache.eval(
		"if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end",
		1,
		key,
		token,
	)


def remove_older_cards(cache_path, older):
	"""A card keeps one file: the files of its older versions go."""
	for path in older:
		if path != cache_path:
			try:
				os.remove(path)
			except FileNotFoundError:
				pass


def digest(text):
	# NOT frappe.generate_hash: it ignores its input and returns a random token, which defeats the cache.
	return hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()[:16]
