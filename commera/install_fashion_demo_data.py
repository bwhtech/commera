import frappe

from commera.install_demo_data import (
	create_configurator,
	create_item_price,
	ensure_warehouse_exists,
	get_root_item_group,
)
from commera.telemetry import data_source

IMAGE_ROOT = "/assets/commera/themes/summer_theme/images"

# Knitted cotton t-shirts. Eight digits, because GST Settings.min_hsn_digits defaults to 6 and
# only 4/6/8 are accepted - an 8-digit code stays valid whatever a site raises that floor to.
DEMO_HSN_CODE = "61091000"

CAR_PART_TEMPLATES = ("BRAKE-PADS", "AIR-FILTER", "FLOOR-MATS")
CAR_PART_CATEGORIES = ("Engine Parts", "Brake System", "Interior Accessories")

BRAND = "Summer"

FASHION_COLORS = (
	("Pink", "PNK"),
	("Purple", "PUR"),
	("Blush", "BLS"),
	("Crimson", "CRM"),
	("Maroon", "MRN"),
	("Rust", "RST"),
)

FASHION_ITEM_GROUPS = ("Knitwear", "Suits", "Denim", "Activewear", "Shirts")

LEGACY_FLAT_CATEGORIES = FASHION_ITEM_GROUPS

# Tab -> mega-menu column -> leaf listing, the three levels Ecommerce Category allows.
FASHION_MENU = (
	{
		"display_name": "Women",
		"children": (
			{
				"display_name": "Clothing",
				"children": (
					{"display_name": "Knitwear", "item_group": "Knitwear"},
					{"display_name": "Suits", "item_group": "Suits"},
					{"display_name": "Shirts", "item_group": "Shirts"},
				),
			},
			{
				"display_name": "Denim & Active",
				"children": (
					{"display_name": "Denim", "item_group": "Denim"},
					{"display_name": "Activewear", "item_group": "Activewear"},
				),
			},
		),
	},
	{
		"display_name": "Men",
		"children": (
			{
				"display_name": "Clothing",
				"children": (
					{"display_name": "Shirts", "item_group": "Shirts"},
					{"display_name": "Suits", "item_group": "Suits"},
				),
			},
			{
				"display_name": "Denim & Active",
				"children": (
					{"display_name": "Denim", "item_group": "Denim"},
					{"display_name": "Activewear", "item_group": "Activewear"},
				),
			},
		),
	},
)

DEFAULT_SIZES = ("S", "M", "L", "XL")

FASHION_PRODUCTS = (
	{
		"code": "KNIT-CARDIGAN",
		"name": "Cozy Knit Cardigan Sweater",
		"item_group": "Knitwear",
		"description": "Soft brushed-knit cardigan with a relaxed shoulder and ribbed cuffs for layering.",
		"base_price": 129.00,
		"sale_price": 99.00,
		"variants": (
			{"color": "Pink", "images": ("shop/product/1.png", "shop/product-2/1.png")},
			{"color": "Purple", "images": ("shop/product/2.png", "shop/product-2/2.png")},
		),
	},
	{
		"code": "SWAGGER-SUIT",
		"name": "Sophisticated Swagger Suit",
		"item_group": "Suits",
		"description": "Tailored two-piece suit in a fluid crepe weave, cut for a clean single-breasted line.",
		"base_price": 349.00,
		"sale_price": 279.00,
		"variants": (
			{"color": "Pink", "images": ("shop/product/5.png", "shop/product/8.png")},
			{"color": "Gray", "images": ("shop/product/7.png",)},
			{"color": "Blush", "images": ("shop/product/6.png",)},
		),
	},
	{
		"code": "DENIM-SKINNY-JEANS",
		"name": "Classic Denim Skinny Jeans",
		"item_group": "Denim",
		"description": "Mid-rise stretch denim with a tapered skinny leg and a lived-in wash.",
		"base_price": 119.00,
		"sale_price": 89.00,
		"variants": (
			{"color": "Blue", "images": ("shop/product/clothes/4.png",)},
			{"color": "Navy", "images": ("shop/product/clothes/5.png",)},
		),
	},
	{
		"code": "MESH-LEGGINGS",
		"name": "Athletic Mesh Sports Leggings",
		"item_group": "Activewear",
		"description": "High-waist training leggings with mesh ventilation panels and a hidden key pocket.",
		"base_price": 79.00,
		"sale_price": 59.00,
		"variants": (
			{"color": "Red", "images": ("products/lady-1.png", "products/lady-3.png")},
			{"color": "Crimson", "images": ("products/lady-2.png",)},
		),
	},
	{
		"code": "DENIM-OVERALL-SHORTS",
		"name": "Vintage Denim Overalls Shorts",
		"item_group": "Denim",
		"description": "Vintage-wash denim shorts with raw frayed hems and a relaxed vintage fit.",
		"base_price": 89.00,
		"sale_price": 69.00,
		"variants": ({"color": "Blue", "images": ("shop/product/clothes/2.png",)},),
	},
	{
		"code": "PRINTED-SPREAD-SHIRT",
		"name": "Printed Spread Collar Casual Shirt",
		"item_group": "Shirts",
		"description": "Printed cotton shirt with a spread collar and roll-up sleeve tabs.",
		"base_price": 69.00,
		"sale_price": 54.00,
		"variants": (
			{"color": "Maroon", "images": ("shop/product/shart/5.png",)},
			{"color": "Rust", "images": ("shop/product/shart/2.png",)},
		),
	},
	{
		"code": "CHECKERED-SLIM-SHIRT",
		"name": "Checkered Slim Collar Casual Shirt",
		"item_group": "Shirts",
		"description": "Slim-collar checkered shirt in a brushed cotton twill, trimmed close through the body.",
		"base_price": 69.00,
		"sale_price": 52.00,
		"variants": (
			{"color": "Blue", "images": ("shop/product/shart/1.png",)},
			{"color": "Navy", "images": ("shop/product/shart/4.png",)},
		),
	},
	{
		"code": "SOLID-CUTAWAY-SHIRT",
		"name": "Solid Cut Away Collar Casual Shirt",
		"item_group": "Shirts",
		"description": "Solid-dyed shirt with a cut-away collar and a soft unlined placket.",
		"base_price": 64.00,
		"sale_price": 49.00,
		"variants": (
			{"color": "Gray", "images": ("shop/product/clothes/3.png",)},
			{"color": "Green", "images": ("shop/product/medium/2.png",)},
		),
	},
	{
		"code": "CHECKERED-SPREAD-SHIRT",
		"name": "Checkered Spread Collar Casual Shirt",
		"item_group": "Shirts",
		"description": "Gingham-checked shirt with a spread collar and a straight boxy hem.",
		"base_price": 66.00,
		"sale_price": 51.00,
		"variants": (
			{"color": "Red", "images": ("shop/product/shart/3.png",)},
			{"color": "White", "images": ("shop/product/clothes/1.png",)},
		),
	},
)


@data_source("demo_data")
def install_fashion_demo_data():
	"""Seed the fashion catalogue and retire the car-part one. Safe to re-run."""
	add_color_attribute_values()
	save_brand()
	save_item_groups()
	save_ecommerce_categories()

	for product in FASHION_PRODUCTS:
		save_product(product)

	receive_opening_stock()
	unpublish_car_part_variants()

	# nosemgrep: frappe-manual-commit  # installer script, runs outside a request
	frappe.db.commit()
	frappe.clear_cache()


def add_color_attribute_values():
	"""Append the fashion colours the car-part seed never needed to the shared Color attribute."""
	attribute = frappe.get_doc("Item Attribute", "Color")
	existing_values = {row.attribute_value for row in attribute.item_attribute_values}

	added = False
	for value, abbreviation in FASHION_COLORS:
		if value not in existing_values:
			attribute.append("item_attribute_values", {"attribute_value": value, "abbr": abbreviation})
			added = True

	if added:
		attribute.save(ignore_permissions=True)


def save_brand():
	if not frappe.db.exists("Brand", BRAND):
		frappe.get_doc({"doctype": "Brand", "brand": BRAND}).insert(ignore_permissions=True)


def save_item_groups():
	parent = "Ecommerce Website"
	if not frappe.db.exists("Item Group", parent):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": parent,
				"is_group": True,
				"parent_item_group": get_root_item_group(),
				"custom_displayname": parent,
			}
		).insert(ignore_permissions=True)

	for item_group in FASHION_ITEM_GROUPS:
		if not frappe.db.exists("Item Group", item_group):
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": item_group,
					"is_group": True,
					"parent_item_group": parent,
					"custom_displayname": item_group,
				}
			).insert(ignore_permissions=True)


def save_ecommerce_categories():
	"""The three-level storefront menu from FASHION_MENU, and the car-part categories switched off."""
	remove_legacy_flat_categories()

	for display_order, tab in enumerate(FASHION_MENU, start=1):
		save_menu_branch(tab, parent=None, root_display_name=tab["display_name"], display_order=display_order)

	for category in CAR_PART_CATEGORIES:
		if frappe.db.exists("Ecommerce Category", category):
			frappe.db.set_value("Ecommerce Category", category, "enabled", 0)


def remove_legacy_flat_categories():
	"""Drop the flat demo categories the tree replaces — their names are the ones a leaf would want.

	Deepest-first: NestedSet refuses to trash a node with children, and delete_doc reclaims the band.
	"""
	legacy_names = frappe.get_all(
		"Ecommerce Category",
		filters={"name": ["in", LEGACY_FLAT_CATEGORIES]},
		order_by="lft desc",
		pluck="name",
	)
	for name in legacy_names:
		frappe.delete_doc("Ecommerce Category", name, ignore_permissions=True)


def save_menu_branch(node, parent, root_display_name, display_order):
	"""Upsert one menu entry and its subtree, parents first so validate_depth always sees height 0."""
	children = node.get("children") or ()
	category = save_category(node, parent, root_display_name, display_order, bool(children))

	for child_order, child in enumerate(children, start=1):
		save_menu_branch(child, category.name, root_display_name, child_order)

	return category


def save_category(node, parent, root_display_name, display_order, is_group):
	"""category_name is the primary key, so "Clothing" can exist only once site-wide; display_name is the label."""
	display_name = node["display_name"]
	category_name = display_name if not parent else f"{root_display_name} {display_name}"

	if frappe.db.exists("Ecommerce Category", category_name):
		category = frappe.get_doc("Ecommerce Category", category_name)
	else:
		category = frappe.new_doc("Ecommerce Category")
		category.category_name = category_name

	category.display_name = display_name
	# Assigning parent and saving is the NestedSet move path; a db_set would not reseat lft/rgt.
	category.parent_ecommerce_category = parent
	category.is_group = 1 if is_group else 0
	category.display_order = display_order
	category.enabled = 1
	# Only a tab owns a storefront URL; validate_route_slug clears the slug on everything below one.
	category.route_slug = None if parent else frappe.scrub(category_name).replace("_", "-")
	category.link_type = "" if is_group else "Item Group"
	category.link_item_groups = []
	if node.get("item_group"):
		category.append("link_item_groups", {"item_group": node["item_group"]})

	category.save(ignore_permissions=True)
	return category


def apply_demo_hsn_code(item):
	"""india_compliance makes gst_hsn_code mandatory on every sales Item, then reads its tax rows
	back through GST HSN Code - so the code must be one that app's own fixtures shipped."""
	if "india_compliance" not in frappe.get_installed_apps():
		return

	if frappe.db.exists("GST HSN Code", DEMO_HSN_CODE):
		item.gst_hsn_code = DEMO_HSN_CODE


def save_product(product):
	template = save_item_template(product)
	configurator = create_configurator(template.name, product)

	for variant in product["variants"]:
		save_style_variant(configurator.name, template.name, product, variant)
		save_item_variants(template.name, product, variant)


def save_item_template(product):
	if frappe.db.exists("Item", product["code"]):
		return frappe.get_doc("Item", product["code"])

	color_values = frappe.get_all(
		"Item Attribute Value", filters={"parent": "Color"}, pluck="attribute_value"
	)
	size_values = frappe.get_all("Item Attribute Value", filters={"parent": "Size"}, pluck="attribute_value")

	template = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": product["code"],
			"item_name": product["name"],
			"item_group": product["item_group"],
			"brand": BRAND,
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"include_item_in_manufacturing": 0,
			"has_variants": 1,
			"variant_based_on": "Item Attribute",
			"description": product["description"],
			"custom_displayname": product["name"],
			"attributes": [
				{"attribute": "Color", "attribute_value": "\n".join(color_values)},
				{"attribute": "Size", "attribute_value": "\n".join(size_values)},
			],
		}
	)
	apply_demo_hsn_code(template)
	template.insert(ignore_permissions=True)
	return template


def save_style_variant(configurator, template_name, product, variant):
	"""The storefront card reads the first `images` row, so the photography lives there, not on og_image."""
	color = variant["color"]
	existing = frappe.db.get_value(
		"Style Attribute Variant", {"configurator": configurator, "attribute_value": color}, "name"
	)
	if existing:
		return frappe.get_doc("Style Attribute Variant", existing)

	style_variant = frappe.get_doc(
		{
			"doctype": "Style Attribute Variant",
			"configurator": configurator,
			"item_style": template_name,
			"attribute_value": color,
			"attribute_name": "Color",
			"display_name": f"{product['name']} - {color}",
			"item_group": product["item_group"],
			"is_published": 1,
			"route": f"{product['code'].lower()}-{color.lower()}",
			"images": [{"image": f"{IMAGE_ROOT}/{image}"} for image in variant["images"]],
		}
	)
	style_variant.insert(ignore_permissions=True)
	return style_variant


def save_item_variants(template_name, product, variant):
	"""Create one sellable Item per size, price it, and map it onto the style variant's size table.

	Published here, not at insert: unpublish_if_incomplete_data rejects a variant with no sizes yet.
	"""
	color = variant["color"]
	style_variant = frappe.get_doc(
		"Style Attribute Variant", {"item_style": template_name, "attribute_value": color}
	)
	mapped_sizes = {row.size for row in style_variant.sizes}

	for size in DEFAULT_SIZES:
		item_code = f"{product['code']}-{color[:3].upper()}-{size}"

		if not frappe.db.exists("Item", item_code):
			variant = frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": item_code,
					"item_name": f"{product['name']} - {color} - {size}",
					"item_group": product["item_group"],
					"brand": BRAND,
					"stock_uom": "Nos",
					"is_stock_item": 1,
					"variant_of": template_name,
					"description": product["description"],
					"custom_displayname": f"{product['name']} {color} {size}",
					"attributes": [
						{"attribute": "Color", "attribute_value": color},
						{"attribute": "Size", "attribute_value": size},
					],
					"valuation_rate": product["base_price"] * 0.5,
				}
			)
			apply_demo_hsn_code(variant)
			variant.insert(ignore_permissions=True)

		create_item_price(item_code, "Standard Selling", product["base_price"])
		create_item_price(item_code, "Sale Price List", product["sale_price"])

		if size not in mapped_sizes:
			style_variant.append("sizes", {"size": size, "item_code": item_code})

	style_variant.is_published = 1
	style_variant.save(ignore_permissions=True)


def receive_opening_stock(qty_per_item=25):
	"""Stock every unstocked fashion item in the ecommerce warehouse so the storefront sells them."""
	warehouse = frappe.get_cached_doc("Commera Settings").ecommerce_warehouse or ensure_warehouse_exists()
	company = frappe.db.get_value("Warehouse", warehouse, "company")
	item_codes = frappe.get_all(
		"Item",
		filters={"variant_of": ["in", [product["code"] for product in FASHION_PRODUCTS]]},
		pluck="name",
	)
	stocked = set(
		frappe.get_all(
			"Bin",
			filters={"item_code": ["in", item_codes], "warehouse": warehouse},
			pluck="item_code",
		)
	)
	pending = [item_code for item_code in item_codes if item_code not in stocked]
	if not pending:
		return

	stock_entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"company": company,
			"to_warehouse": warehouse,
			"items": [
				{
					"item_code": item_code,
					"qty": qty_per_item,
					"t_warehouse": warehouse,
					"basic_rate": 10,
				}
				for item_code in pending
			],
		}
	)
	stock_entry.insert(ignore_permissions=True)
	stock_entry.submit()


def unpublish_car_part_variants():
	"""Hide the car-part demo from the storefront without deleting it — flip is_published back to restore."""
	car_part_variants = frappe.get_all(
		"Style Attribute Variant",
		filters={"item_style": ["in", CAR_PART_TEMPLATES], "is_published": 1},
		pluck="name",
	)
	for variant_name in car_part_variants:
		# Saved through the doc so the search index sync hook drops them from the storefront index too.
		variant = frappe.get_doc("Style Attribute Variant", variant_name)
		variant.is_published = 0
		variant.save(ignore_permissions=True)

	return car_part_variants
