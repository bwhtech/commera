from html import unescape
from urllib.parse import quote, urlsplit, urlunsplit

import frappe
from frappe.utils import cstr, flt, get_url, strip_html_tags

from commera.branding import get_configured_brand_assets
from commera.localization import alternates, get_localization, get_request_path
from commera.localization.urls import get_locale_roots, get_og_locale
from commera.localization.urls import url as localized_url
from commera.store_frame import get_shop_details
from commera.utils import get_store_currency

META_DESCRIPTION_MAX_LENGTH = 160

# Satori card of the store's logo and name, served by www/og_image_render.
DEFAULT_OG_IMAGE = "/og-image/store.png"


def get_default_og_image() -> str:
	"""The store card in the request's language and market: its name and tagline are translated."""
	return localized_url(DEFAULT_OG_IMAGE)


def get_product_og_image(route: str) -> str:
	"""A product's card under the request's locale prefix, so each language and market has its own."""
	return localized_url(f"/og-image/{route}.png")


def encode_url_path(url):
	parts = urlsplit(url)
	safe_path = quote(parts.path, safe="/%")
	return urlunsplit((parts.scheme, parts.netloc, safe_path, parts.query, parts.fragment))


def absolute_url(path_or_url):
	if not path_or_url:
		return ""
	if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
		return encode_url_path(path_or_url)
	return encode_url_path(get_url(path_or_url))


def truncate_description(text):
	# Plain text: the seo macro escapes it, so an entity left here would show as "&amp;amp;".
	clean = unescape(strip_html_tags(frappe.utils.cstr(text or ""))).strip()
	clean = " ".join(clean.split())
	if len(clean) <= META_DESCRIPTION_MAX_LENGTH:
		return clean
	truncated = clean[: META_DESCRIPTION_MAX_LENGTH - 1].rsplit(" ", 1)[0]
	return f"{truncated}…"


def current_request_url():
	return get_url(get_request_path() or None)


def get_store_name():
	"""The store name in the request language."""
	return get_shop_details().name or "Store"


def get_store_description():
	"""The store description in the request language, or blank."""
	return get_shop_details().description


def default_store_description():
	"""Non-empty meta-description fallback so no page (esp. the homepage) ships a blank one."""
	store_name = get_store_name()
	return truncate_description(f"Shop the latest collections and styles at {store_name}.")


def get_seo_settings():
	return frappe.get_cached_doc("Commera Settings", "Commera Settings")


class BlankDefaultMap(dict):
	def __missing__(self, key):
		return ""


def apply_title_template(title=None):
	store_name = get_store_name()
	template = get_seo_settings().get("seo_title_template") or "{title} | {store}"
	if not title:
		return store_name
	try:
		return template.format_map(BlankDefaultMap(title=title, store=store_name))
	except Exception:
		return f"{title} | {store_name}"


def get_site_currency():
	return get_store_currency()


def get_og_locales() -> dict:
	"""og:locale of the request and og:locale:alternate of every other locale root."""
	locale = get_og_locale(get_localization())
	others = []
	for root in get_locale_roots():
		if root.og_locale not in (locale, *others):
			others.append(root.og_locale)
	return {"locale": locale, "alternates": others}


def schema_availability(availability):
	if availability == "InStock":
		return "https://schema.org/InStock"
	if availability == "OutOfStock":
		return "https://schema.org/OutOfStock"
	return None


def build_product_seo(
	product_variant,
	product,
	image_url,
	price=None,
	availability=None,
	lang="en",
	currency=None,
):
	store_name = get_store_name()
	display_name = product_variant.get("display_name") or product.get("item_name") or store_name

	meta_title = product_variant.get("meta_title") or f"{display_name} | {store_name}"

	fallback_description = product_variant.get("description") or product.get("description") or display_name
	meta_description = truncate_description(product_variant.get("meta_description") or fallback_description)

	og_override = product_variant.get("og_image")
	resolved_image = absolute_url(og_override or image_url or get_default_og_image())

	request_path = get_request_path()
	canonical = get_url(request_path) if request_path else current_request_url()

	return {
		"title": meta_title,
		"description": meta_description,
		"image": resolved_image,
		"url": canonical,
		"type": "product",
		"alternates": alternates(request_path or None),
		"price": f"{flt(price):.2f}" if price else None,
		"currency": (currency or get_site_currency()) if price else None,
		"availability": availability,
		"noindex": bool(product_variant.get("noindex")),
	}


def build_product_json_ld(
	product_variant,
	product,
	images,
	price=None,
	availability=None,
	currency=None,
	review_count=None,
	average_rating=None,
):
	override = product_variant.get("json_ld")
	if override:
		# orjson raises straight through frappe.parse_json, so a half-edited override falls back to generated.
		try:
			parsed = frappe.parse_json(override)
		except Exception:
			frappe.log_error(title=f"Invalid json_ld override on {product_variant.get('name')}")
			parsed = None
		if parsed:
			return parsed

	display_name = product_variant.get("display_name") or product.get("item_name")
	description = truncate_description(
		product_variant.get("meta_description")
		or product_variant.get("description")
		or product.get("description")
		or display_name
	)
	image_list = [absolute_url(image) for image in (images or []) if image]

	request_path = get_request_path()
	product_url = get_url(request_path) if request_path else current_request_url()

	sku = product.get("item_code") or product_variant.get("item_style")

	json_ld = {
		"@context": "https://schema.org",
		"@type": "Product",
		"name": display_name,
		"image": image_list,
		"description": description,
		"sku": sku,
		"mpn": sku,
	}

	brand = product.get("brand")
	if brand:
		json_ld["brand"] = {"@type": "Brand", "name": brand}

	if price:
		offer = {
			"@type": "Offer",
			"price": f"{flt(price):.2f}",
			"priceCurrency": currency or get_site_currency(),
			"url": product_url,
		}
		schema_avail = schema_availability(availability)
		if schema_avail:
			offer["availability"] = schema_avail
		json_ld["offers"] = offer

	# An aggregateRating with zero reviews is penalised by Google's rich-result validator, so the
	# key is omitted entirely rather than emitted with reviewCount: 0.
	if review_count:
		json_ld["aggregateRating"] = {
			"@type": "AggregateRating",
			"ratingValue": f"{flt(average_rating):.1f}",
			"reviewCount": review_count,
		}

	return json_ld


@frappe.whitelist()
def generate_product_json_ld(variant: str | int):
	# Deferred import: product_detail pulls in utils, which imports from seo at module top.
	from commera.product_detail import get_product_detail

	frappe.has_permission("Style Attribute Variant", "read", variant, throw=True)

	route = frappe.db.get_value("Style Attribute Variant", variant, "route")
	detail = get_product_detail(route) if route else None
	if not detail:
		frappe.throw(frappe._("Could not load product detail for this variant."))

	product_variant = detail["product_variant"]
	# Ignore any stored override so the button always previews the generated shape.
	product_variant.json_ld = None

	schema = build_product_json_ld(
		product_variant,
		detail["product"],
		images=detail["images"],
		price=detail["selected_price"],
		availability="InStock" if detail["in_stock"] else "OutOfStock",
	)
	return frappe.as_json(schema, indent=2)


def build_breadcrumb_json_ld(breadcrumbs):
	items = []
	position = 1
	for crumb in breadcrumbs or []:
		label = crumb.get("label")
		if not label:
			continue
		element = {
			"@type": "ListItem",
			"position": position,
			"name": label,
		}
		href = crumb.get("href")
		if href and href not in ("#", ""):
			element["item"] = absolute_url(href)
		items.append(element)
		position += 1

	return {
		"@context": "https://schema.org",
		"@type": "BreadcrumbList",
		"itemListElement": items,
	}


def build_page_seo(source, display_name=None, page_type="website"):
	settings = get_seo_settings()

	meta_title = source.get("meta_title")
	title = meta_title or apply_title_template(display_name)

	meta_description = source.get("meta_description")
	description = (
		truncate_description(meta_description)
		if meta_description
		else (get_store_description() or default_store_description())
	)

	image = source.get("og_image") or settings.get("default_share_image") or get_default_og_image()

	request_path = get_request_path()
	canonical = get_url(request_path) if request_path else current_request_url()

	return {
		"title": title,
		"description": description,
		"image": absolute_url(image),
		"url": canonical,
		"type": page_type,
		"alternates": alternates(request_path or None),
		"price": None,
		"currency": None,
		"availability": None,
		"noindex": bool(source.get("noindex")),
	}


def build_collection_seo(category, breadcrumbs, total_count=0, lang="en", image_url=None, category_doc=None):
	store_name = get_store_name()
	overrides = category_doc or {}

	settings = {} if category else get_seo_settings()

	meta_title = overrides.get("meta_title") or (
		None if category else settings.get("product_list_meta_title")
	)
	title = meta_title or (f"{category} | {store_name}" if category else f"Products | {store_name}")

	meta_description = overrides.get("meta_description") or (
		None if category else settings.get("product_list_meta_description")
	)
	if meta_description:
		description = truncate_description(meta_description)
	elif category:
		description = truncate_description(
			f"Shop {category} at {store_name}. Browse {total_count} products with the latest styles."
		)
	else:
		description = truncate_description(f"Shop the latest products at {store_name}.")

	resolved_image = overrides.get("og_image") or (
		None if category else settings.get("product_list_og_image")
	)

	request_path = get_request_path()
	canonical = get_url(request_path) if request_path else current_request_url()

	return {
		"title": title,
		"description": description,
		"image": absolute_url(resolved_image or image_url or get_default_og_image()),
		"url": canonical,
		"type": "website",
		"alternates": alternates(request_path or None),
		"price": None,
		"currency": None,
		"availability": None,
		"noindex": bool(overrides.get("noindex")),
	}


def build_collection_json_ld(category, breadcrumbs, total_count=0):
	store_name = get_store_name()
	name = f"{category} | {store_name}" if category else f"Products | {store_name}"

	request_path = get_request_path()
	page_url = get_url(request_path) if request_path else current_request_url()

	return {
		"@context": "https://schema.org",
		"@type": "CollectionPage",
		"name": name,
		"url": page_url,
		"numberOfItems": total_count,
	}


def default_seo():
	settings = get_seo_settings()

	image = settings.get("default_share_image") or get_default_og_image()

	return {
		"title": apply_title_template(),
		"description": get_store_description() or default_store_description(),
		"image": absolute_url(image),
		"url": current_request_url(),
		"type": "website",
		"alternates": [],
		"price": None,
		"currency": None,
		"availability": None,
	}


def org_website_json_ld():
	settings = get_seo_settings()
	store_name = get_store_name()
	favicon = get_configured_brand_assets()["favicon"]
	site_url = get_url()

	organization = {
		"@context": "https://schema.org",
		"@type": "Organization",
		"name": store_name,
		"url": site_url,
	}
	if favicon:
		organization["logo"] = absolute_url(favicon)

	same_as = [
		settings.get("facebook_url"),
		settings.get("twitter_url"),
		settings.get("instagram_url"),
	]
	same_as = [url for url in same_as if url]
	if same_as:
		organization["sameAs"] = same_as

	website = {
		"@context": "https://schema.org",
		"@type": "WebSite",
		"name": store_name,
		"url": site_url,
		"potentialAction": {
			"@type": "SearchAction",
			"target": {
				"@type": "EntryPoint",
				"urlTemplate": f"{site_url}/products?search={{search_term_string}}",
			},
			"query-input": "required name=search_term_string",
		},
	}

	return [organization, website]
