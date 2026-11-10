import frappe
from frappe.utils import cint, create_batch, cstr, flt

from commera.base_prices import base_price_filters
from commera.card_prices import get_card_price
from commera.commera_ecommerce.doctype.ecommerce_category.ecommerce_category import root_filter
from commera.search.translations import get_market_titles, get_translated_titles
from commera.utils import IN_CLAUSE_CHUNK_SIZE

# The only doctypes reachable from a variant (itself, its Item, its Style Attribute Configurator).
ALLOWED_CONTENT_DOCTYPES = ("Item", "Style Attribute Variant", "Style Attribute Configurator")

# Only free-text fieldtypes carry search tokens; anything else (numbers, dates, tables) is skipped.
INDEXABLE_FIELDTYPES = {"Data", "Select", "Small Text", "Text", "Long Text", "Link", "Read Only"}

# Fallback (doctype, field) pairs reproducing the storefront's LIKE search surface.
DEFAULT_CONTENT_FIELDS = (
	("Style Attribute Variant", "display_name"),
	("Style Attribute Variant", "attribute_value"),
	("Style Attribute Variant", "item_group"),
	("Item", "brand"),
)

# Item fields every product record copies, configured or not.
ITEM_FIELDS = ("brand", "is_stock_item", "item_name")


def get_configured_content_fields():
	"""Configured (doctype, field) pairs that feed `content` (allowed + text-typed only), else the defaults."""
	settings = frappe.get_cached_doc("Commera Settings")
	configured = [
		(row.search_doctype, row.field)
		for row in (settings.search_content_fields or [])
		if is_indexable_content_field(row.search_doctype, row.field)
	]
	return configured or list(DEFAULT_CONTENT_FIELDS)


def is_indexable_content_field(doctype, field):
	"""True when (doctype, field) is an allowed, text-typed field that exists as a column on this site."""
	if doctype not in ALLOWED_CONTENT_DOCTYPES or not field:
		return False
	meta_field = frappe.get_meta(doctype).get_field(field)
	if not meta_field or meta_field.fieldtype not in INDEXABLE_FIELDTYPES:
		return False
	# has_column guards columns in meta but absent on this site: get_all would raise, so the pair is dropped.
	return frappe.db.has_column(doctype, field)


def fields_by_doctype(configured_fields, doctype):
	"""The field names of the configured (doctype, field) pairs that belong to `doctype`, in order."""
	return [field for pair_doctype, field in configured_fields if pair_doctype == doctype]


def union_fields(base_fields, extra_fields):
	"""base_fields plus any extra_fields not already present, order-preserving (for get_all field lists)."""
	fields = list(base_fields)
	for field in extra_fields:
		if field not in fields:
			fields.append(field)
	return fields


def get_indexable_docs(doctype, filters, names, fields):
	"""Rows matching `filters`, narrowed to `names` when given.
	`names` is chunked (one huge IN(...) falls over); `None` means every row, `[]` means nothing - never collapse them.
	"""
	if names is None:
		return frappe.get_all(doctype, filters=filters, fields=fields)

	rows = []
	for chunk in create_batch(list(names), IN_CLAUSE_CHUNK_SIZE):
		rows.extend(frappe.get_all(doctype, filters={**filters, "name": ("in", chunk)}, fields=fields))
	return rows


def build_product_search_records(variant_names=None):
	configured_fields = get_configured_content_fields()
	variant_content_fields = fields_by_doctype(configured_fields, "Style Attribute Variant")
	item_content_fields = fields_by_doctype(configured_fields, "Item")
	configurator_content_fields = fields_by_doctype(configured_fields, "Style Attribute Configurator")

	base_variant_fields = [
		"name",
		"display_name",
		"attribute_value",
		"item_group",
		"item_style",
		"route",
		"modified",
		"configurator",
	]
	# `is_published` stays ANDed with the name filter so a since-unpublished variant is deleted, not re-added.
	variants = get_indexable_docs(
		"Style Attribute Variant",
		{"is_published": 1},
		variant_names,
		union_fields(base_variant_fields, variant_content_fields),
	)
	if not variants:
		return []

	item_styles = list({variant.item_style for variant in variants if variant.item_style})
	item_by_style = items_for_item_styles(item_styles, item_content_fields)

	configurator_names = list({variant.configurator for variant in variants if variant.configurator})
	configurator_by_name = configurators_for(configurator_names, configurator_content_fields)

	names = [variant.name for variant in variants]
	sizes_by_variant = sizes_for_variants(names)
	images_by_variant = images_for_variants(names)
	prices_by_variant = prices_for_variants(sizes_by_variant)
	titles_by_variant = get_translated_titles("Style Attribute Variant", variants)
	market_titles = get_market_titles("Style Attribute Variant", names)

	records = []
	for variant in variants:
		item = item_by_style.get(variant.item_style) or {}
		configurator = configurator_by_name.get(variant.configurator) or {}
		titles = titles_by_variant[variant.name]
		records.append(
			{
				"name": variant.name,
				"title": variant.display_name or "",
				"content": join_text(build_content(configured_fields, variant, item, configurator), titles),
				"titles": titles,
				"market_titles": market_titles.get(variant.name, {}),
				"item_group": variant.item_group or "",
				"brand": item.get("brand") or "",
				"color": variant.attribute_value or "",
				"sizes": sizes_by_variant.get(variant.name, []),
				"detail": build_product_detail(
					variant,
					item,
					sizes_by_variant.get(variant.name, []),
					images_by_variant.get(variant.name, {}),
					prices_by_variant.get(variant.name, {}),
				),
			}
		)
	return records


def build_content(configured_fields, variant, item, configurator):
	"""Join the resolved value of each configured (doctype, field) pair, in order, into `content`."""
	source_by_doctype = {
		"Style Attribute Variant": variant,
		"Item": item,
		"Style Attribute Configurator": configurator,
	}
	parts = []
	for doctype, field in configured_fields:
		value = cstr(source_by_doctype[doctype].get(field)).strip()
		if value:
			parts.append(value)
	return " ".join(parts).strip()


def join_text(content, titles):
	"""`content` followed by the translated titles, so a query in any published language finds the record."""
	return " ".join([content, *titles.values()]).strip()


def build_product_detail(variant, item, sizes, images, prices):
	"""The full product-card snapshot stored in the index's product_detail table."""
	detail = {
		"name": variant.name,
		"route": variant.route or "",
		"item_style": variant.item_style or "",
		"display_name": variant.display_name or "",
		"attribute_value": variant.attribute_value or "",
		"brand": item.get("brand") or "",
		"is_stock_item": cint(item.get("is_stock_item")),
		"item_name": item.get("item_name") or "",
		"variant_item_code": sizes[0]["item_code"] if sizes else "",
		"image": images.get("image") or "",
		"hover_image": images.get("hover_image") or "",
		"item_group": variant.item_group or "",
		"color": variant.attribute_value or "",
		"modified": cstr(variant.modified) if variant.modified else None,
	}
	detail.update(prices)
	return detail


def get_root_route_slugs():
	"""(lft, rgt, route_slug) of every menu root, so a nested entry can borrow a landable slug.
	Only roots own a `route_slug`; without the borrow a child hit lands on `/products?category=`.
	"""
	return frappe.get_all(
		"Ecommerce Category",
		filters={"parent_ecommerce_category": root_filter()},
		fields=["lft", "rgt", "route_slug"],
	)


def build_category_search_records(names=None):
	# `enabled` stays ANDed with the name filter for the same reason as `is_published` above.
	categories = get_indexable_docs(
		"Ecommerce Category",
		{"enabled": 1},
		names,
		["name", "category_name", "display_name", "route_slug", "lft"],
	)
	if not categories:
		return []

	roots = get_root_route_slugs()
	titles_by_category = get_translated_titles("Ecommerce Category", categories)
	market_titles = get_market_titles("Ecommerce Category", [category.name for category in categories])

	records = []
	for category in categories:
		category_name = category.category_name or ""
		display_name = category.display_name or ""
		route_slug = category.route_slug or ""
		if not route_slug:
			route_slug = next(
				(
					root.route_slug
					for root in roots
					if root.route_slug and root.lft <= category.lft <= root.rgt
				),
				"",
			)
		records.append(
			{
				"name": category.name,
				"title": display_name or category_name,
				"content": join_text(
					" ".join(part for part in (category_name, display_name) if part),
					titles_by_category[category.name],
				),
				"route_slug": route_slug,
				"market_titles": market_titles.get(category.name, {}),
			}
		)
	return records


def items_for_item_styles(item_styles, content_fields=None):
	"""Map item_style (Item name) -> {brand, is_stock_item, item_name, ...content}."""
	fields = union_fields(["name", *ITEM_FIELDS], content_fields or [])

	item_by_style = {}
	for chunk in create_batch(item_styles, IN_CLAUSE_CHUNK_SIZE):
		for item in frappe.get_all("Item", filters={"name": ("in", chunk)}, fields=fields):
			item_by_style[item.name] = item
	return item_by_style


def configurators_for(configurator_names, content_fields):
	"""Map Style Attribute Configurator name -> {field: value} for the configured content fields."""
	if not content_fields:
		return {}
	fields = union_fields(["name"], content_fields)
	configurator_by_name = {}
	for chunk in create_batch(configurator_names, IN_CLAUSE_CHUNK_SIZE):
		for configurator in frappe.get_all(
			"Style Attribute Configurator", filters={"name": ("in", chunk)}, fields=fields
		):
			configurator_by_name[configurator.name] = configurator
	return configurator_by_name


def sizes_for_variants(variant_names):
	"""Map variant -> ordered [{size, item_code}] (idx order), one batched fetch per chunk."""
	sizes_by_variant = {}
	for chunk in create_batch(variant_names, IN_CLAUSE_CHUNK_SIZE):
		for row in frappe.get_all(
			"Color Size Item",
			filters={"parent": ("in", chunk), "parenttype": "Style Attribute Variant"},
			fields=["parent", "size", "item_code", "idx"],
			order_by="parent asc, idx asc",
		):
			sizes_by_variant.setdefault(row.parent, []).append(
				{"size": row.size or "", "item_code": row.item_code or ""}
			)
	return sizes_by_variant


def images_for_variants(variant_names):
	"""Map variant -> {image (slideshow idx 1), hover_image (idx 2)}."""
	images_by_variant = {}
	for chunk in create_batch(variant_names, IN_CLAUSE_CHUNK_SIZE):
		for row in frappe.get_all(
			"Website Slideshow Item",
			filters={
				"parent": ("in", chunk),
				"parenttype": "Style Attribute Variant",
				"idx": ("in", [1, 2]),
			},
			fields=["parent", "idx", "image"],
			order_by="parent asc, idx asc",
		):
			slot = "image" if row.idx == 1 else "hover_image"
			images_by_variant.setdefault(row.parent, {}).setdefault(slot, row.image)
	return images_by_variant


def prices_for_variants(sizes_by_variant):
	"""Map variant -> price snapshot, aggregating Item Price over the variant's item_codes."""
	settings = frappe.get_cached_doc("Commera Settings")
	default_price_list = settings.default_price_list
	sale_price_list = settings.sale_price_list

	codes_by_variant = {
		variant: [size["item_code"] for size in sizes if size.get("item_code")]
		for variant, sizes in sizes_by_variant.items()
	}
	all_codes = list({code for codes in codes_by_variant.values() for code in codes})
	default_rate, sale_rate, sale_upto = rates_by_item_code(all_codes, default_price_list, sale_price_list)

	snapshots = {
		variant: aggregate_prices(codes, default_rate, sale_rate, sale_upto)
		for variant, codes in codes_by_variant.items()
	}
	# The index keeps 0 for an unpriced product, as before.
	for snapshot in snapshots.values():
		snapshot["effective_price"] = flt(snapshot["effective_price"])
	return snapshots


def rates_by_item_code(item_codes, default_price_list, sale_price_list):
	"""Per item_code: min default rate, min sale rate, max sale valid_upto across Item Price rows."""
	default_rate, sale_rate, sale_upto = {}, {}, {}
	for chunk in create_batch(item_codes, IN_CLAUSE_CHUNK_SIZE):
		for row in frappe.get_all(
			"Item Price",
			filters=base_price_filters(
				{"item_code": ("in", chunk), "price_list": ("in", [default_price_list, sale_price_list])}
			),
			fields=["item_code", "price_list", "price_list_rate", "valid_upto"],
		):
			if row.price_list == default_price_list and row.price_list_rate is not None:
				default_rate[row.item_code] = min_or(default_rate.get(row.item_code), row.price_list_rate)
			if row.price_list == sale_price_list and row.price_list_rate is not None:
				sale_rate[row.item_code] = min_or(sale_rate.get(row.item_code), row.price_list_rate)
				if row.valid_upto:
					sale_upto[row.item_code] = max_or(sale_upto.get(row.item_code), row.valid_upto)
	return default_rate, sale_rate, sale_upto


def aggregate_prices(item_codes, default_rate, sale_rate, sale_upto):
	"""A product's card prices over its sizes (card_prices.get_card_price), with its last sale end."""
	upto_values = [sale_upto[code] for code in item_codes if code in sale_upto]
	return {
		**get_card_price([(sale_rate.get(code), default_rate.get(code)) for code in item_codes]),
		"sale_end_date": max(upto_values) if upto_values else None,
	}


def min_or(current, value):
	return value if current is None else min(current, value)


def max_or(current, value):
	return value if current is None else max(current, value)
