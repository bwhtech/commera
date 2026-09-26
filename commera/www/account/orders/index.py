no_cache = True

import frappe
from frappe.query_builder import DocType
from pypika import CustomFunction, Order

from commera.utils import get_current_page


def get_context(context):
	current_user = frappe.session.user
	if current_user == "Guest":
		raise frappe.PermissionError
	page = get_current_page()
	context.return_period = frappe.get_cached_value("Commera Settings", "Commera Settings", "return_period")
	context.page_length = 6
	context.current_page = page
	total_count, orders = get_orders_list(
		page=page,
		page_length=context.page_length,
	)
	context.orders = orders
	context.total_count = total_count
	return_reasons = frappe.get_cached_value("Commera Settings", "Commera Settings", "reason_for_return")
	context.return_reasons = [
		{"name": return_reason.name, "display_name": return_reason.display_name}
		for return_reason in return_reasons
	]
	context.breadcrumbs = [
		{
			"label": "My Account",
			"href": f"/{frappe.local.lang}/account/",
		},
		{
			"label": "Orders",
			"href": "#",
		},
	]


def get_orders_list(order_id_list=None, page=1, page_length=6):
	sales_order = DocType("Sales Order")
	sales_order_item = DocType("Sales Order Item")
	style_attribute_variant = DocType("Style Attribute Variant")
	color_size_item = DocType("Color Size Item")
	website_slideshow_item = DocType("Website Slideshow Item")
	item = DocType("Item")
	payment_entry = DocType("Payment Entry")
	payment_entry_reference = DocType("Payment Entry Reference")
	item_variant_attribute = DocType("Item Variant Attribute")
	warehouse = DocType("Warehouse")
	dynamic_link = DocType("Dynamic Link")
	address = DocType("Address")
	JSON_ARRAYAGG = CustomFunction("JSON_ARRAYAGG", ["value"])

	first_image_query = (
		frappe.qb.from_(website_slideshow_item)
		.where(website_slideshow_item.parent == style_attribute_variant.name)
		.select(website_slideshow_item.image)
		.limit(1)
	)
	json_object_args = [
		"brand",
		item.brand,
		"item_name",
		item.item_name,
		"price",
		sales_order_item.amount,
		"image",
		first_image_query,
		"item_code",
		sales_order_item.item_code,
		"is_free_item",
		sales_order_item.is_free_item,
		"size",
		color_size_item.size,
	]
	has_custom_name_ar = frappe.db.has_column("Item", "custom_item_name_ar")
	if has_custom_name_ar:
		json_object_args.append("item_name_ar")
		json_object_args.append(item.custom_item_name_ar)
	num_keys = len(json_object_args) // 2
	arg_names = []
	for i in range(1, num_keys + 1):
		arg_names += [f"key{i}", f"value{i}"]
	JSON_OBJECT = CustomFunction("JSON_OBJECT", arg_names)
	base_query = (
		frappe.qb.from_(sales_order_item)
		.left_join(sales_order)
		.on(sales_order_item.parent == sales_order.name)
		.left_join(color_size_item)
		.on(sales_order_item.item_code == color_size_item.item_code)
		.left_join(style_attribute_variant)
		.on(color_size_item.parent == style_attribute_variant.name)
		.left_join(item)
		.on(item.name == style_attribute_variant.item_style)
		.left_join(item_variant_attribute)
		.on(item_variant_attribute.parent == sales_order_item.item_code)
		.left_join(payment_entry_reference)
		.on(payment_entry_reference.reference_name == sales_order.name)
		.left_join(warehouse)
		.on(warehouse.name == sales_order.custom_store)
		.left_join(dynamic_link)
		.on(
			(dynamic_link.link_doctype == "Warehouse")
			& (dynamic_link.link_name == warehouse.name)
			& (dynamic_link.parenttype == "Address")
		)
		.left_join(address)
		.on(address.name == dynamic_link.parent)
		.left_join(payment_entry)
		.on(payment_entry_reference.parent == payment_entry.name)
		.where(item_variant_attribute.attribute == "Size")
		.where(sales_order.owner == frappe.session.user)
	)

	if order_id_list:
		base_query = base_query.where(sales_order.name.isin(order_id_list))

	total_count_query = base_query.select(sales_order.name).distinct()
	total_count = len(total_count_query.run(as_dict=True))

	paginated_query = (
		base_query.select(
			sales_order.name,
			sales_order.custom_ecommerce_status,
			sales_order.custom_ecommerce_payment_mode,
			sales_order.creation,
			sales_order.billing_status,
			sales_order.rounded_total,
			sales_order.total,
			sales_order.net_total,
			sales_order.total_taxes_and_charges,
			sales_order.rounding_adjustment,
			sales_order.shipping_rule,
			sales_order.shipping_address,
			sales_order.custom_is_store_pickup,
			address.address_line1.as_("pickup_address_line_1"),
			address.address_line2.as_("pickup_address_line_2"),
			address.city.as_("pickup_city"),
			address.state.as_("pickup_state"),
			address.pincode.as_("pickup_pincode"),
			address.phone.as_("pickup_phone"),
			JSON_ARRAYAGG(JSON_OBJECT(*json_object_args)).as_("items"),
		)
		.groupby(sales_order.name)
		.orderby(sales_order.creation, order=Order.desc)
		.limit(page_length)
		.offset((page - 1) * page_length)
	)

	orders = paginated_query.run(as_dict=True)

	return total_count, orders
