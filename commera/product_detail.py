import frappe
from frappe.utils import cstr, flt

from commera.base_prices import get_sales_units
from commera.localization.market_prices import MarketPrices
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
	# get_doc of a missing record queues a "not found" message that reaches the response even when caught.
	name = frappe.db.get_value("Style Attribute Variant", {"route": route, "is_published": 1}, "name")
	if not name:
		return None
	product_variant = frappe.get_doc("Style Attribute Variant", name)

	product = frappe.get_doc("Item", product_variant.item_style)
	commera_settings = frappe.get_cached_doc("Commera Settings")
	warehouse = commera_settings.ecommerce_warehouse

	prices = MarketPrices.current()
	available_sizes = get_available_sizes(product_variant, warehouse)
	price_sizes(available_sizes, prices)
	selected_item = get_selected_item(available_sizes, selected_size)
	if not selected_item:
		selected_item = available_sizes[0] if available_sizes else None

	selected_price = (selected_item or {}).get("price")
	if prices.uses_store_prices:
		default_price = flt((selected_item or {}).get("compare_at_rate"))
		sale_price = (selected_item or {}).get("sale_rate")
	else:
		default_price = (selected_item or {}).get("compare_at_price")
		sale_price = selected_price

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
		"currency": prices.currency,
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


def price_sizes(sizes, prices):
	"""Price each size in the market, per its sales unit. A size with no price today is not for sale."""
	item_codes = [row["item_code"] for row in sizes]
	sale, compare_at = prices.get_base_rates(item_codes)
	units = get_sales_units(item_codes)
	for row in sizes:
		item_code = row["item_code"]
		row["unit"] = units.get(item_code)
		# None and 0.0 stay distinct: "not on this list" falls back, "free" does not.
		row["sale_rate"], row["compare_at_rate"] = sale.get(item_code), compare_at.get(item_code)
		row["price"] = prices.price(sale.get(item_code), compare_at.get(item_code))
		row["compare_at_price"] = prices.compare_at(row["price"], compare_at.get(item_code))
		if row["price"] is None:
			row["stock_detail"] = {**row["stock_detail"], "in_stock": False}
