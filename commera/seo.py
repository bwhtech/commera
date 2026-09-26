from urllib.parse import quote, urlsplit, urlunsplit

import frappe
from frappe.utils import cstr, flt, get_url, strip_html_tags

from commera.branding import get_configured_brand_assets

META_DESCRIPTION_MAX_LENGTH = 160

DEFAULT_OG_IMAGE = "/assets/commera/images/1.jpg"

# Storefront languages, in hreflang emission order; the first is the x-default target.
LANGUAGES = ("en", "ar")


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
	clean = strip_html_tags(frappe.utils.cstr(text or "")).strip()
	clean = " ".join(clean.split())
	if len(clean) <= META_DESCRIPTION_MAX_LENGTH:
		return clean
	truncated = clean[: META_DESCRIPTION_MAX_LENGTH - 1].rsplit(" ", 1)[0]
	return f"{truncated}…"


def current_request_url():
	path = getattr(frappe.local, "request", None)
	if path and getattr(path, "path", None):
		return get_url(frappe.local.request.path)
	return get_url()


def get_store_name():
	return get_seo_settings().get("store_name") or "Store"


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
	return cstr(frappe.db.get_single_value("Global Defaults", "default_currency")) or "INR"


def swap_lang_in_path(path, target_lang):
	if not path:
		return f"/{target_lang}/"
	parts = path.split("/")
	if len(parts) > 1 and parts[1] in LANGUAGES:
		parts[1] = target_lang
		return "/".join(parts)
	return f"/{target_lang}{path}"


def build_alternates(path):
	return [{"lang": lang, "href": get_url(swap_lang_in_path(path, lang))} for lang in LANGUAGES]


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
	resolved_image = absolute_url(og_override or image_url or DEFAULT_OG_IMAGE)

	request_path = frappe.local.request.path if getattr(frappe.local, "request", None) else ""
	canonical = get_url(request_path) if request_path else current_request_url()

	return {
		"title": meta_title,
		"description": meta_description,
		"image": resolved_image,
		"url": canonical,
		"type": "product",
		"alternates": build_alternates(request_path),
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

	request_path = frappe.local.request.path if getattr(frappe.local, "request", None) else ""
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
		else (settings.get("default_meta_description") or default_store_description())
	)

	image = (
		source.get("og_image")
		or settings.get("default_share_image")
		or get_configured_brand_assets()["favicon"]
		or DEFAULT_OG_IMAGE
	)

	request_path = frappe.local.request.path if getattr(frappe.local, "request", None) else ""
	canonical = get_url(request_path) if request_path else current_request_url()

	return {
		"title": title,
		"description": description,
		"image": absolute_url(image),
		"url": canonical,
		"type": page_type,
		"alternates": build_alternates(request_path),
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

	request_path = frappe.local.request.path if getattr(frappe.local, "request", None) else ""
	canonical = get_url(request_path) if request_path else current_request_url()

	return {
		"title": title,
		"description": description,
		"image": absolute_url(resolved_image or image_url or DEFAULT_OG_IMAGE),
		"url": canonical,
		"type": "website",
		"alternates": build_alternates(request_path),
		"price": None,
		"currency": None,
		"availability": None,
		"noindex": bool(overrides.get("noindex")),
	}


def build_collection_json_ld(category, breadcrumbs, total_count=0):
	store_name = get_store_name()
	name = f"{category} | {store_name}" if category else f"Products | {store_name}"

	request_path = frappe.local.request.path if getattr(frappe.local, "request", None) else ""
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

	image = (
		settings.get("default_share_image") or get_configured_brand_assets()["favicon"] or DEFAULT_OG_IMAGE
	)

	return {
		"title": apply_title_template(),
		"description": settings.get("default_meta_description") or default_store_description(),
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
				"urlTemplate": f"{site_url}/en/products?search={{search_term_string}}",
			},
			"query-input": "required name=search_term_string",
		},
	}

	return [organization, website]
