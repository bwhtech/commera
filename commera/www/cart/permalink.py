from urllib.parse import quote, urlencode

import frappe
from frappe import _
from frappe.utils.data import cint, cstr

from commera.api.cart import get_cart_price
from commera.guest import is_guest, is_guest_checkout_enabled
from commera.product_detail import size_sort_key
from commera.utils import get_available_stocks

no_cache = True

MAX_CART_LINES = 25
FORWARDED_PARAM_PREFIXES = ("utm_", "checkout[")


def get_context(context):
	redirect_to_language_route()
	requested_quantities, notices = parse_cart_codes(frappe.form_dict.get("codes"))
	context.lines = get_cart_lines(requested_quantities, notices)
	context.notices = notices
	context.next_url = get_next_url() if context.lines else f"/{frappe.local.lang}/cart"


def redirect_to_language_route():
	request = getattr(frappe.local, "request", None)
	if not request or request.path.startswith(("/en/", "/ar/")):
		return

	# Not a website_redirects rule: that rebuilds the target from the decoded path, so a "?" in an item code
	# would start the query string.
	target = f"/en/cart/{quote(cstr(frappe.form_dict.get('codes')), safe=':,')}"
	if query_string := frappe.safe_decode(request.query_string):
		target = f"{target}?{query_string}"
	frappe.redirect(target)


def parse_cart_codes(codes: str | None) -> tuple[dict[str, int], list[str]]:
	requested_quantities = {}
	notices = []
	max_pairs = MAX_CART_LINES * 2
	pairs = cstr(codes).split(",", max_pairs)
	skipped_count = pairs.pop().count(",") + 1 if len(pairs) > max_pairs else 0
	for pair in pairs:
		pair = pair.strip()
		if not pair:
			continue

		item_code, separator, qty = pair.rpartition(":")
		if not separator:
			item_code, qty = pair, "1"
		item_code = item_code.strip()
		if not item_code or not qty.strip().isdigit() or cint(qty) < 1:
			notices.append(_("{0} was skipped: the quantity must be a whole number above zero.").format(pair))
			continue

		if item_code not in requested_quantities and len(requested_quantities) >= MAX_CART_LINES:
			skipped_count += 1
			continue
		requested_quantities[item_code] = requested_quantities.get(item_code, 0) + cint(qty)

	if skipped_count:
		notices.append(
			_("{0} more products were skipped: a cart link holds at most {1} products.").format(
				skipped_count, MAX_CART_LINES
			)
		)
	return requested_quantities, notices


def get_cart_lines(requested_quantities: dict[str, int], notices: list[str]) -> list[dict]:
	if not requested_quantities:
		return []

	size_row_by_item_code = {row.item_code: row for row in get_sellable_size_rows(list(requested_quantities))}
	variant_names = list({row.parent for row in size_row_by_item_code.values()})
	sizes_by_variant = get_sizes_by_variant(variant_names)
	stock_detail_by_item_code = {
		size["item_code"]: size["stock_detail"] for sizes in sizes_by_variant.values() for size in sizes
	}
	variant_by_name = get_variants(variant_names)
	commera_settings = frappe.get_cached_doc("Commera Settings")
	price_lists = (commera_settings.get_default_price_list(), commera_settings.get_sale_price_list())

	lines = []
	for item_code, requested_qty in requested_quantities.items():
		size_row = size_row_by_item_code.get(item_code)
		if not size_row:
			notices.append(_("{0} is not available.").format(item_code))
			continue

		stock_detail = stock_detail_by_item_code[item_code]
		in_stock_qty = cint(stock_detail.get("stock_qty"))
		if in_stock_qty < 1:
			notices.append(_("{0} is out of stock.").format(size_row.item_name))
			continue
		if requested_qty > in_stock_qty:
			notices.append(
				_("Only {0} of {1} are in stock, so the quantity was lowered.").format(
					in_stock_qty, size_row.item_name
				)
			)

		default_price, price = get_cart_price(item_code, *price_lists)
		variant = variant_by_name[size_row.parent]
		lines.append(
			{
				"item": variant,
				"variant": {
					"item_code": item_code,
					"size": size_row.size,
					"stock_detail": stock_detail,
					"item_name": size_row.item_name,
					"item_name_ar": size_row.get("item_name_ar") or size_row.item_name,
				},
				"qty": min(requested_qty, in_stock_qty),
				"price": price,
				"default_price": default_price,
				"brand": variant.brand or "",
				"sizes": sizes_by_variant[size_row.parent],
			}
		)

	return lines


def get_sellable_size_rows(item_codes: list[str]) -> list[dict]:
	color_size_item = frappe.qb.DocType("Color Size Item")
	style_attribute_variant = frappe.qb.DocType("Style Attribute Variant")
	item = frappe.qb.DocType("Item")
	query = (
		frappe.qb.from_(color_size_item)
		.join(style_attribute_variant)
		.on(style_attribute_variant.name == color_size_item.parent)
		.join(item)
		.on(item.name == color_size_item.item_code)
		.select(color_size_item.item_code, color_size_item.size, color_size_item.parent, item.item_name)
		.where(color_size_item.parenttype == "Style Attribute Variant")
		.where(color_size_item.item_code.isin(item_codes))
		.where(style_attribute_variant.is_published == 1)
		.where(item.disabled == 0)
	)
	if frappe.db.has_column("Item", "custom_item_name_ar"):
		query = query.select(item.custom_item_name_ar.as_("item_name_ar"))
	return query.run(as_dict=True)


def get_sizes_by_variant(variant_names: list[str]) -> dict[str, list[dict]]:
	if not variant_names:
		return {}

	size_rows = frappe.get_all(
		"Color Size Item",
		filters={"parenttype": "Style Attribute Variant", "parent": ["in", variant_names]},
		fields=["parent", "item_code", "size"],
	)
	warehouse = frappe.get_cached_value("Commera Settings", "Commera Settings", "ecommerce_warehouse")
	stock_by_item_code = get_available_stocks([row.item_code for row in size_rows], warehouse)

	sizes_by_variant = {variant_name: [] for variant_name in variant_names}
	for row in size_rows:
		sizes_by_variant[row.parent].append(
			{"item_code": row.item_code, "size": row.size, "stock_detail": stock_by_item_code[row.item_code]}
		)
	for sizes in sizes_by_variant.values():
		sizes.sort(key=lambda size: size_sort_key(size["size"]))
	return sizes_by_variant


def get_variants(variant_names: list[str]) -> dict[str, dict]:
	if not variant_names:
		return {}

	style_attribute_variant = frappe.qb.DocType("Style Attribute Variant")
	item = frappe.qb.DocType("Item")
	variants = (
		frappe.qb.from_(style_attribute_variant)
		.left_join(item)
		.on(item.name == style_attribute_variant.item_style)
		.select(
			style_attribute_variant.name,
			style_attribute_variant.display_name,
			style_attribute_variant.route,
			style_attribute_variant.item_style,
			item.brand,
		)
		.where(style_attribute_variant.name.isin(variant_names))
	).run(as_dict=True)
	images = frappe.get_all(
		"Website Slideshow Item",
		filters={"parenttype": "Style Attribute Variant", "parent": ["in", variant_names]},
		fields=["parent", "image"],
		order_by="idx asc",
	)

	variant_by_name = {variant.name: frappe._dict(variant, images=[]) for variant in variants}
	for image in images:
		variant_by_name[image.parent].images.append({"image": image.image})
	return variant_by_name


def get_next_url() -> str:
	forwarded_params = [
		(key, value)
		for key, value in frappe.form_dict.items()
		if key == "discount" or key.startswith(FORWARDED_PARAM_PREFIXES)
	]
	cart_url = f"/{frappe.local.lang}/cart"
	if not is_guest():
		forwarded_params = [("checkout", "1"), *forwarded_params]
	elif is_guest_checkout_enabled():
		cart_url = f"{cart_url}/checkout"
	query_string = urlencode(forwarded_params, doseq=True)
	return f"{cart_url}?{query_string}" if query_string else cart_url
