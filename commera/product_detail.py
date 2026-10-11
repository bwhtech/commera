import frappe
from frappe.utils import cstr, flt

from commera.utils import get_available_stock, get_discount_percent

DEFAULT_PRODUCT_IMAGE = "/assets/commera/images/1.jpg"

SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]


def size_sort_key(size):
	"""Sort key ranking numeric sizes by value, then known letter sizes by SIZE_ORDER, unknown letters last."""
	try:
		return (0, float(size), "")
	except (TypeError, ValueError):
		size_label = cstr(size).upper()
		rank = SIZE_ORDER.index(size_label) if size_label in SIZE_ORDER else len(SIZE_ORDER)
		return (1, rank, size_label)


def get_product_detail(route, selected_size=None):
	try:
		product_variant = frappe.get_doc("Style Attribute Variant", {"route": route})
	except frappe.DoesNotExistError:
		return None

	if not product_variant.is_published:
		return None

	product = frappe.get_doc("Item", product_variant.item_style)
	commera_settings = frappe.get_cached_doc("Commera Settings")
	warehouse = commera_settings.ecommerce_warehouse

	available_sizes = get_available_sizes(product_variant, warehouse)
	selected_item = get_selected_item(available_sizes, selected_size)
	if not selected_item:
		selected_item = available_sizes[0] if available_sizes else None

	default_price = flt(get_price(selected_item, commera_settings.get_default_price_list()))
	sale_price = get_price(selected_item, commera_settings.get_sale_price_list())
	selected_price = sale_price if sale_price is not None else default_price

	images = (
		[image.image for image in product_variant.images]
		if product_variant.images
		else [DEFAULT_PRODUCT_IMAGE]
	)

	return {
		"product_variant": product_variant,
		"product": product,
		"images": images,
		"available_sizes": available_sizes,
		"selected_size": selected_size or (selected_item or {}).get("size"),
		"selected_item": selected_item,
		"default_price": default_price,
		"sale_price": sale_price,
		"selected_price": selected_price,
		"discount_percent": get_discount_percent(default_price, sale_price),
		"in_stock": bool((selected_item or {}).get("stock_detail", {}).get("in_stock")),
		"warehouse": warehouse,
	}


def get_available_sizes(product_variant, warehouse):
	sizes = [
		{
			"item_code": size.item_code,
			"size": size.size,
			"stock_detail": get_available_stock(size.item_code, warehouse),
		}
		for size in product_variant.sizes
	]
	if not sizes:
		return []

	return sorted(sizes, key=lambda row: size_sort_key(row["size"]))


def get_selected_item(available_sizes, selected_size):
	return next(
		(row for row in available_sizes if row["size"] == selected_size),
		next((row for row in available_sizes if row["stock_detail"].get("in_stock") == 1), None),
	)


def get_price(selected_item, price_list):
	"""Rate for the item on this price list, or None when it has no row there."""
	# None and 0.0 must stay distinguishable: "not on this list" falls back, "free" does not.
	if not selected_item:
		return None
	price = frappe.get_cached_value(
		"Item Price",
		{"item_code": selected_item["item_code"], "price_list": price_list},
		"price_list_rate",
	)
	return flt(price) if price is not None else None
