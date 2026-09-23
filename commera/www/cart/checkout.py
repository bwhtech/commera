import frappe
from bwh_payments.bwh_payments.utils import get_payment_modes_for_currency
from frappe.query_builder import DocType

from commera.core import _get_cart_quotation
from commera.utils import (
	format_addresses,
	get_addresses,
	get_cod_configuration,
	get_country_list,
	get_delivery_configuration,
	get_directions_url,
	get_pickup_addresses,
	get_pickup_warehouses,
)

# from commera.api.utils import auth_required

no_cache = True


# @auth_required
def get_context(context):
	current_user = frappe.session.user
	if current_user == "Guest":
		frappe.redirect(f"/{frappe.local.lang}/cart")
	cart_quotation = _get_cart_quotation()
	if not cart_quotation or not cart_quotation.items:
		frappe.redirect(f"/{frappe.local.lang}/cart")
	commera_settings = frappe.get_cached_doc("Commera Settings")
	default_price_list = commera_settings.get("default_price_list")
	context.payment_gateways = get_payment_modes_for_currency(cart_quotation.currency)
	context.show_cod = commera_settings.get("cod_enabled", 0)
	context.cart_quotation = cart_quotation
	context.coupon_code = get_coupon_code(cart_quotation)
	context.country_list = get_country_list()
	items = get_checkout_items(cart_quotation)
	if default_price_list:
		for item in items:
			item["default_price"] = frappe.get_cached_value(
				"Item Price",
				{"item_code": item.item_code, "price_list": default_price_list},
				"price_list_rate",
			)
	context.items = items
	context.billing_addresses = get_addresses()
	context.shipping_addresses = get_addresses(address_type="Shipping")
	context.store_pickup_addresses = (
		get_store_pickup_addresses() if commera_settings.store_pickup_enabled else []
	)
	context.delivery_charge, context.delivery_charge_applicable_below = get_delivery_configuration()
	context.cod_charge_applicable_below, context.cod_charge = get_cod_configuration()
	context.breadcrumbs = [
		{
			"label": "Cart",
			"href": f"/{frappe.local.lang}/cart/",
		},
		{
			"label": "Checkout",
			"href": "#",
		},
	]


def get_coupon_code(cart_quotation):
	coupon_code = ""
	try:
		coupon_code = frappe.get_cached_value("Coupon Code", cart_quotation.coupon_code, "coupon_code")
	except Exception:
		pass
	return coupon_code


def get_checkout_items(cart_quotation):
	quotation_item = DocType("Quotation Item")
	style_attribute_variant = DocType("Style Attribute Variant")
	color_size_item = DocType("Color Size Item")
	website_slideshow_item = DocType("Website Slideshow Item")
	item = DocType("Item")
	item_variant_attribute = DocType("Item Variant Attribute")
	has_custom_name_ar = frappe.db.has_column("Item", "custom_item_name_ar")
	query = (
		frappe.qb.from_(color_size_item)
		.left_join(quotation_item)
		.on(quotation_item.item_code == color_size_item.item_code)
		.left_join(style_attribute_variant)
		.on(color_size_item.parent == style_attribute_variant.name)
		.left_join(website_slideshow_item)
		.on(website_slideshow_item.parent == style_attribute_variant.name)
		.left_join(item)
		.on(item.name == style_attribute_variant.item_style)
		.left_join(item_variant_attribute)
		.on(item_variant_attribute.parent == quotation_item.item_code)
		.where(quotation_item.parent == cart_quotation.name)
		.where(item_variant_attribute.attribute == "Size")
		.select(
			style_attribute_variant.name,
			style_attribute_variant.item_style,
			style_attribute_variant.display_name,
			item.brand,
			item.item_name,
			website_slideshow_item.image.as_("image"),
			quotation_item.item_code,
			quotation_item.qty,
			quotation_item.rate,
			quotation_item.price_list_rate,
			quotation_item.amount,
			item_variant_attribute.attribute_value.as_("size"),
		)
		.groupby(quotation_item.name)
	)
	if has_custom_name_ar:
		query = query.select(item.custom_item_name_ar.as_("custom_item_name_ar"))
	return query.run(as_dict=True)


def get_store_pickup_addresses():
	# Not cached: an owner who adds a pickup address in the dashboard expects checkout to offer it now.
	options = []
	for warehouse, address in get_pickup_addresses(get_pickup_warehouses()).items():
		option = format_addresses([address], address_type="Shop")[0]
		option["warehouse_name"] = warehouse
		option["directions_url"] = get_directions_url(address.custom_store_location)
		options.append(option)
	return options
