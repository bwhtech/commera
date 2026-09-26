"""Shared OG card render core for the live /og-image endpoint and the admin preview button."""

import base64
import os
import subprocess
import time
from io import BytesIO
from urllib.parse import urlsplit

import frappe
from frappe.utils import flt, get_files_path, get_url

from commera import seo
from commera.branding import get_brand_assets
from commera.shop_themes.render import render_themed_template

# resvg-js is pathologically slow on large embedded images (~58s for 1220x1760, <1s downscaled).
CARD_PHOTO_PX = 700

# Social card spec used by Facebook/X/LinkedIn; 1.91:1 ratio.
DEFAULT_OG_WIDTH = 1200
DEFAULT_OG_HEIGHT = 630

BUNDLED_CARD_TEMPLATE = "commera/templates/og/product_card.html"
STORE_CARD_TEMPLATE = "commera/templates/og/store_card.html"

# Tall enough for a crisp logo at the card's 140px display height, small enough to keep resvg fast.
CARD_LOGO_PX = 420


def render_og_png(html_str, width, height):
	font_weights = [("OpenSans-Regular.ttf", 400), ("OpenSans-Bold.ttf", 700)]
	fonts = [
		{
			"path": frappe.get_app_path("commera", "public", "fonts", "OpenSans", filename),
			"name": "OpenSans",
			"weight": weight,
			"style": "normal",
		}
		for filename, weight in font_weights
	]
	payload = {"html": html_str, "width": width, "height": height, "fonts": fonts}

	# .mjs, not .js: satori is ESM-only and the app root also holds CJS tooling.
	script_path = frappe.get_app_path("commera", "og", "og_satori.mjs")
	payload_bytes = frappe.as_json(payload).encode()
	# node is on PATH on benches; the satori toolchain resolves via the app's node_modules.
	try:
		result = subprocess.run(
			["node", script_path],
			input=payload_bytes,
			capture_output=True,
			cwd=frappe.get_app_path("commera"),
			timeout=30,
		)
	except subprocess.TimeoutExpired:
		frappe.throw(frappe._("OG card render timed out"))

	if result.returncode != 0:
		frappe.throw(f"satori render failed: {result.stderr.decode(errors='replace')}")

	return result.stdout


def build_variant_card_context(variant_doc):
	from commera.product_detail import get_product_detail

	detail = get_product_detail(variant_doc.route)
	brand = ""
	price = ""
	photo_data_uri = None
	if detail:
		brand = detail["product"].brand or ""
		amount = detail["sale_price"] or detail["default_price"]
		if amount:
			price = f"{seo.get_site_currency()} {flt(amount):.2f}"
		images = detail["images"]
		if images:
			photo_data_uri = product_image_data_uri(images[0])

	return {
		"store_name": seo.get_store_name(),
		"display_name": variant_doc.display_name or variant_doc.name,
		"brand": brand,
		"price": price,
		"photo_data_uri": photo_data_uri,
		# DocType templates address the source document as `doc`.
		"doc": variant_doc,
	}


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


def render_card_for_doc(for_doctype, doc):
	context = context_builder_for(for_doctype)(doc)
	# nosemgrep: frappe-ssti  # template is admin-authored OG Image Template, not end-user input
	html_str = render_themed_template(resolve_template(for_doctype), context)
	return render_og_png(html_str, DEFAULT_OG_WIDTH, DEFAULT_OG_HEIGHT)


def build_store_card_html():
	settings = seo.get_seo_settings()
	context = {
		"store_name": seo.get_store_name(),
		"tagline": settings.get("default_meta_description") or seo.default_store_description(),
		"site_host": urlsplit(get_url()).hostname or "",
		"logo_data_uri": logo_data_uri(get_brand_assets().logo),
	}
	return render_themed_template(STORE_CARD_TEMPLATE, context)


def variant_primary_image_url(variant_name):
	return frappe.db.get_value(
		"Website Slideshow Item",
		{"parent": variant_name, "parenttype": "Style Attribute Variant"},
		"image",
		order_by="idx asc",
	)


def local_image_path(image_url):
	# Satori can't fetch remote URLs offline, so only local files can be inlined as data URIs.
	if image_url.startswith("/files/"):
		path = get_files_path(image_url[len("/files/") :], is_private=False)
	elif image_url.startswith("/private/files/"):
		path = get_files_path(image_url[len("/private/files/") :], is_private=True)
	elif image_url.startswith("/assets/"):
		assets_root = os.path.abspath(os.path.join(frappe.local.sites_path, "assets"))
		path = os.path.abspath(os.path.join(frappe.local.sites_path, image_url.lstrip("/")))
		if not path.startswith(assets_root + os.sep):
			return None
	else:
		return None

	return path if os.path.exists(path) else None


def logo_data_uri(image_url):
	path = local_image_path(image_url)
	if not path:
		return None

	# nosemgrep: frappe-security-file-traversal  # local_image_path confines the path to files/ or assets/
	with open(path, "rb") as logo_file:
		raw = logo_file.read()
	if path.lower().endswith(".svg"):
		return f"data:image/svg+xml;base64,{base64.b64encode(raw).decode()}"

	from PIL import Image

	# PNG, not the product photo's JPEG: a logo's transparency must survive onto the card background.
	image = Image.open(BytesIO(raw)).convert("RGBA")
	image.thumbnail((CARD_LOGO_PX * 3, CARD_LOGO_PX))
	buffer = BytesIO()
	image.save(buffer, format="PNG")
	return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"


def product_image_data_uri(image_url):
	path = local_image_path(image_url)
	if not path:
		return None

	from PIL import Image

	image = Image.open(path)
	image.thumbnail((CARD_PHOTO_PX, CARD_PHOTO_PX))
	# Always emit JPEG: a downscaled PNG can still be ~800KB, and resvg is slow on large blobs.
	if image.mode == "RGBA" or (image.mode == "P" and "transparency" in image.info):
		flattened = Image.new("RGB", image.size, (255, 255, 255))
		rgba = image.convert("RGBA")
		flattened.paste(rgba, mask=rgba.split()[-1])
		image = flattened
	else:
		image = image.convert("RGB")

	buffer = BytesIO()
	image.save(buffer, format="JPEG", quality=85)
	encoded = base64.b64encode(buffer.getvalue()).decode()
	return f"data:image/jpeg;base64,{encoded}"


# Keyed on route+modified, so every edit strands the previous card; bound the directory.
CARD_CACHE_MAX_AGE_DAYS = 30


def clear_old_cards(days=CARD_CACHE_MAX_AGE_DAYS):
	cache_dir = os.path.join(get_files_path(is_private=False), "og-cache")
	if not os.path.isdir(cache_dir):
		return

	cutoff = time.time() - (days * 86400)
	for filename in os.listdir(cache_dir):
		if not filename.endswith(".png"):
			continue
		path = os.path.join(cache_dir, filename)
		if os.path.getmtime(path) < cutoff:
			os.remove(path)
