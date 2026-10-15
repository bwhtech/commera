import random

import frappe
from frappe import _
from frappe.utils import cint, flt, fmt_money, random_string

STANDARD_DELIVERY_OPTION = "Standard Delivery"


def install_demo_data():
	"""Main function to install all demo data"""
	frappe.flags.in_demo_data = True

	print("\n" + "=" * 60)
	print("Installing Commera Demo Data")
	print("=" * 60 + "\n")

	try:
		# Step 1: Prerequisites
		print("Step 1: Creating Prerequisites...")
		create_item_attributes()
		create_brands()
		create_price_lists()
		create_shipping_rule()

		# Step 2: Configure Commera Settings
		print("\nStep 2: Configuring Commera Settings...")
		configure_commera_settings()
		# Step 2.1: Create Ecommerce Structure
		print("\nStep 2.1: Creating Ecommerce Structure...")
		create_ecommerce_group()
		create_ecommerce_categories()
		create_default_footer_sections()

		# Step 3: Create demo products
		print("\nStep 3: Creating Demo Products...")
		create_demo_products()

		# Step 4: Publish Style Attribute Variants
		print("\nStep 4: Publishing Style Attribute Variants...")
		publish_style_variants()

		# Website Item ships with webshop, which this app does not depend on; the storefront reads SAVs.
		if frappe.db.exists("DocType", "Website Item"):
			print("\nStep 5: Creating and Publishing Website Items...")
			create_website_items()
		else:
			print("\nStep 5: Skipped - webshop is not installed")

		# Step 6: Fix routing
		print("\nStep 6: Fixing Product Routes...")
		fix_product_routes()

		# Step 7: Clear cache
		print("\nStep 7: Clearing Cache...")
		frappe.clear_cache()

		print("\n" + "=" * 60)
		print("✅ Demo Data Installation Complete!")
		print("=" * 60)
		print("\nYou can now access the shop at:")
		print("  English: https://your-site.com/en/products")
		print("  Arabic:  https://your-site.com/ar/products")
		print("\nDemo products created (Car Parts Theme):")
		print("  - Premium Brake Pads (Multiple colors & sizes)")
		print("  - High-Flow Air Filter (Multiple colors & sizes)")
		print("  - All-Weather Floor Mats (Multiple colors & sizes)")
		print("\nDemo Categories created:")
		print("  - Engine Parts")
		print("  - Brake System")
		print("  - Interior Accessories")
		print("\n")
		# nosemgrep: frappe-manual-commit  # installer script, runs outside a request
		frappe.db.commit()

	except Exception as e:
		frappe.db.rollback()
		print(f"\n❌ Error during demo data installation: {e!s}")
		import traceback

		traceback.print_exc()
		raise
	finally:
		frappe.flags.in_demo_data = False


def create_item_attributes():
	"""Create Item Attributes for variants"""
	print("  - Creating Item Attributes...")

	# Color attribute
	ensure_attribute_values(
		"Color",
		[
			("Red", "RED"),
			("Blue", "BLU"),
			("Black", "BLK"),
			("White", "WHT"),
			("Green", "GRN"),
			("Navy", "NVY"),
			("Gray", "GRY"),
		],
	)

	# Size attribute
	ensure_attribute_values(
		"Size",
		[
			("XS", "XS"),
			("S", "S"),
			("M", "M"),
			("L", "L"),
			("XL", "XL"),
			("XXL", "XXL"),
		],
	)


def ensure_attribute_values(attribute_name, values, numeric=False):
	"""Ensure an Item Attribute exists with all required values"""

	if not frappe.db.exists("Item Attribute", attribute_name):
		# Create new attribute
		attr = frappe.get_doc(
			{
				"doctype": "Item Attribute",
				"attribute_name": attribute_name,
				"numeric_values": 1 if numeric else 0,
				"item_attribute_values": [{"attribute_value": val, "abbr": abbr} for val, abbr in values],
			}
		)
		attr.insert(ignore_permissions=True)
		# nosemgrep: frappe-manual-commit  # installer script, runs outside a request
		frappe.db.commit()
		print(f"    ✓ {attribute_name} attribute created")
	else:
		# Not updated: a changed abbreviation collides with the existing attribute values.
		print(f"    • {attribute_name} attribute already exists")


def create_brands():
	"""Create demo brands"""
	print("  - Creating Brands...")

	brands = ["Brembo", "K&N", "WeatherTech", "Lifestyle Store"]

	for brand_name in brands:
		if not frappe.db.exists("Brand", brand_name):
			brand = frappe.get_doc({"doctype": "Brand", "brand": brand_name})
			brand.insert(ignore_permissions=True)
			print(f"    ✓ Brand '{brand_name}' created")
		else:
			print(f"    • Brand '{brand_name}' already exists")


def create_price_lists():
	"""Create price lists"""
	print("  - Creating Price Lists...")

	price_lists = [
		{"name": "Standard Selling", "currency": "USD", "enabled": 1, "buying": 0, "selling": 1},
		{"name": "Sale Price List", "currency": "USD", "enabled": 1, "buying": 0, "selling": 1},
	]

	for pl_data in price_lists:
		if not frappe.db.exists("Price List", pl_data["name"]):
			pl = frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": pl_data["name"],
					"currency": pl_data["currency"],
					"enabled": pl_data["enabled"],
					"buying": pl_data["buying"],
					"selling": pl_data["selling"],
				}
			)
			pl.insert(ignore_permissions=True)
			print(f"    ✓ Price List '{pl_data['name']}' created")
		else:
			print(f"    • Price List '{pl_data['name']}' already exists")


def save_standard_delivery_option(
	flat_charge: float, free_shipping_above: float, currency: str
) -> str | None:
	"""The delivery option the store's Shipping Rule bands price; created once, then left to the merchant."""
	if "bwh_shipping" not in frappe.get_installed_apps():
		return None
	if frappe.db.exists("Shipping Service", STANDARD_DELIVERY_OPTION):
		return STANDARD_DELIVERY_OPTION

	threshold = fmt_money(free_shipping_above, precision=0, currency=currency)
	service = frappe.new_doc("Shipping Service")
	service.title = STANDARD_DELIVERY_OPTION
	service.enabled = 1
	service.description = f"Delivered in 3-5 business days. Free on orders over {threshold}."
	service.backup_charge = flat_charge
	service.insert(ignore_permissions=True)
	return service.name


def create_shipping_rule():
	"""Create the Standard Shipping rule, or rebuild its bands so a re-seed names the delivery option."""
	print("  - Creating Shipping Rule...")

	company = frappe.defaults.get_user_default("Company") or frappe.db.get_value("Company", {}, "name")
	if not company:
		print("    ⚠ Skipping Shipping Rule creation - no Company found")
		return

	company_abbr = frappe.db.get_value("Company", company, "abbr")
	account = frappe.db.get_value(
		"Account", {"account_name": "Freight and Forwarding Charges", "company": company}, "name"
	)
	if not account:
		account = f"Freight and Forwarding Charges - {company_abbr}"

	cost_center = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
	if not cost_center:
		cost_center = f"Main - {company_abbr}"

	exists = frappe.db.exists("Shipping Rule", "Standard Shipping")
	shipping_rule = (
		frappe.get_doc("Shipping Rule", "Standard Shipping") if exists else frappe.new_doc("Shipping Rule")
	)
	if not exists:
		shipping_rule.update(
			{
				"label": "Standard Shipping",
				"shipping_rule_type": "Selling",
				"calculate_based_on": "Net Total",
				"company": company,
				"account": account,
				"cost_center": cost_center,
			}
		)

	flat_charge, free_shipping_above = 10, 50
	delivery_option = save_standard_delivery_option(
		flat_charge, free_shipping_above, frappe.get_cached_value("Company", company, "default_currency")
	)
	shipping_rule.conditions = []
	shipping_rule.append(
		"conditions",
		{
			"from_value": 0,
			"to_value": free_shipping_above,
			"shipping_amount": flat_charge,
			"shipping_service": delivery_option,
		},
	)
	shipping_rule.append(
		"conditions",
		{
			"from_value": free_shipping_above,
			"to_value": 0,
			"shipping_amount": 0,
			"free_shipping": 1,
			"shipping_service": delivery_option,
		},
	)
	shipping_rule.save(ignore_permissions=True)
	print(f"    ✓ Shipping Rule 'Standard Shipping' {'updated' if exists else 'created'}")


def ensure_warehouse_exists():
	"""Ensure a warehouse exists for demo data"""
	# Try to find existing non-group warehouse
	warehouse = frappe.db.get_value("Warehouse", {"is_group": 0}, "name")

	if warehouse:
		return warehouse

	# Get company
	company = frappe.defaults.get_user_default("Company") or frappe.db.get_value("Company", {}, "name")

	if not company:
		frappe.throw(_("Please create a Company first before running demo data"))

	# Create default warehouse
	company_abbr = frappe.db.get_value("Company", company, "abbr")
	warehouse_name = f"Stores - {company_abbr}"

	if not frappe.db.exists("Warehouse", warehouse_name):
		warehouse = frappe.get_doc(
			{"doctype": "Warehouse", "warehouse_name": "Stores", "company": company, "is_group": 0}
		)
		warehouse.insert(ignore_permissions=True)
		print(f"    ✓ Warehouse '{warehouse_name}' created")
		return warehouse.name

	return warehouse_name


def configure_commera_settings():
	"""Configure Commera Settings"""
	print("  - Configuring Commera Settings...")

	# Ensure warehouse exists
	warehouse = ensure_warehouse_exists()

	# Get or create settings
	if frappe.db.exists("Commera Settings", "Commera Settings"):
		settings = frappe.get_doc("Commera Settings", "Commera Settings")
	else:
		settings = frappe.get_doc({"doctype": "Commera Settings"})

	# Configure settings
	settings.company = frappe.defaults.get_user_default("Company") or frappe.db.get_value(
		"Company", {}, "name"
	)
	settings.default_price_list = "Standard Selling"
	settings.sale_price_list = "Sale Price List"
	settings.ecommerce_warehouse = warehouse
	settings.shipping_rule = (
		"Standard Shipping" if frappe.db.exists("Shipping Rule", "Standard Shipping") else None
	)
	settings.return_period = 30
	settings.cod_enabled = 1
	settings.cod_charge = 5.00
	settings.cod_charge_applicable_below = 100.00

	# Email templates (use existing from fixtures)
	settings.order_confirmation_email_template = "Order Confirmation"
	settings.order_cancellation_email_template = "Order Cancellation"
	settings.item_in_stock_email_template = "Item In Stock"

	# Return reasons
	if not settings.reason_for_return:
		reasons = ["Wrong Size", "Wrong Color", "Defective Product", "Not as Described", "Changed Mind"]
		for reason_text in reasons:
			settings.append("reason_for_return", {"display_name": reason_text})

	settings.save(ignore_permissions=True)
	print("    ✓ Commera Settings configured")


def get_available_attribute_values(attribute_name):
	"""Get all available values for an attribute"""
	if not frappe.db.exists("Item Attribute", attribute_name):
		return []

	return frappe.get_all(
		"Item Attribute Value",
		filters={"parent": attribute_name},
		fields=["attribute_value"],
		pluck="attribute_value",
	)


def create_demo_products():
	"""Create demo product templates and variants"""

	# Get available attribute values from system
	available_colors = get_available_attribute_values("Color")
	available_sizes = get_available_attribute_values("Size")

	if not available_colors:
		print("  ⚠ No Color attribute values found. Skipping demo products.")
		return

	if not available_sizes:
		print("  ⚠ No Size attribute values found. Skipping demo products.")
		return

	# Use only available colors and sizes
	colors_to_use = [c for c in ["Black", "White", "Navy", "Gray", "Blue", "Red"] if c in available_colors]
	sizes_to_use = [s for s in ["XS", "S", "M", "L", "XL", "XXL"] if s in available_sizes]

	if not colors_to_use:
		colors_to_use = available_colors[:4]  # Use first 4 available colors

	if not sizes_to_use:
		sizes_to_use = available_sizes[:5]  # Use first 5 available sizes

	products = [
		{
			"code": "BRAKE-PADS",
			"name": "Premium Brake Pads",
			"item_group": "Brake System",
			"brand": "Lifestyle Store",
			"description": "High-performance ceramic brake pads with superior stopping power and minimal dust.",
			"colors": colors_to_use[:3],
			"sizes": sizes_to_use[:4],
			"base_price": 89.99,
			"sale_price": 74.99,
		},
		{
			"code": "AIR-FILTER",
			"name": "High-Flow Air Filter",
			"item_group": "Engine Parts",
			"brand": "K&N",
			"description": "Performance air filter for improved engine airflow and horsepower. Washable and reusable.",
			"colors": colors_to_use[:2],
			"sizes": sizes_to_use[:3],
			"base_price": 49.99,
			"sale_price": 39.99,
		},
		{
			"code": "FLOOR-MATS",
			"name": "All-Weather Floor Mats",
			"item_group": "Interior Accessories",
			"brand": "Lifestyle Store",
			"description": "Durable rubber floor mats with raised edges to contain spills and debris. Perfect fit guaranteed.",
			"colors": colors_to_use[:4],
			"sizes": sizes_to_use[:5],
			"base_price": 59.99,
			"sale_price": 49.99,
		},
	]

	print(f"  Using {len(colors_to_use)} colors: {', '.join(colors_to_use)}")
	print(f"  Using {len(sizes_to_use)} sizes: {', '.join(sizes_to_use)}")

	for product in products:
		print(f"\n  Creating product: {product['name']}")
		create_product_with_variants(product)


def create_product_with_variants(product_data):
	"""Create a product template with all its variants"""

	# Step 1: Create item template
	template = create_item_template(product_data)
	if not template:
		return

	# Step 2: Create Style Attribute Configurator
	configurator = create_configurator(template.name, product_data)
	if not configurator:
		return

	# Step 3: Create Style Attribute Variants (one per color)
	for color in product_data["colors"]:
		create_style_variant(configurator.name, template.name, color, product_data)

	# Step 4: Create actual item variants and link them
	create_item_variants(template.name, product_data)


def create_item_template(product_data):
	"""Create an item template (parent item with variants)"""

	item_code = product_data["code"]

	if frappe.db.exists("Item", item_code):
		print(f"    • Template '{item_code}' already exists")
		return frappe.get_doc("Item", item_code)

	# Get company for default accounts
	# company = frappe.defaults.get_user_default("Company") or frappe.db.get_value("Company", {}, "name")

	# Get attribute values for template
	color_values = frappe.get_all(
		"Item Attribute Value",
		filters={"parent": "Color"},
		fields=["attribute_value"],
		pluck="attribute_value",
	)

	size_values = frappe.get_all(
		"Item Attribute Value",
		filters={"parent": "Size"},
		fields=["attribute_value"],
		pluck="attribute_value",
	)

	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": product_data["name"],
			"item_group": product_data["item_group"],
			"brand": product_data["brand"],
			"stock_uom": "Nos",
			"is_stock_item": 1,
			"include_item_in_manufacturing": 0,
			"has_variants": 1,
			"variant_based_on": "Item Attribute",
			"description": product_data["description"],
			"custom_displayname": product_data["name"],
			"attributes": [
				{"attribute": "Color", "attribute_value": "\n".join(color_values) if color_values else ""},
				{"attribute": "Size", "attribute_value": "\n".join(size_values) if size_values else ""},
			],
		}
	)

	item.insert(ignore_permissions=True)
	print(f"    ✓ Template '{item_code}' created")
	return item


def create_configurator(template_name, product_data):
	"""Create Style Attribute Configurator"""

	# Check if configurator exists
	existing = frappe.db.get_value("Style Attribute Configurator", {"item_template": template_name}, "name")

	if existing:
		print(f"    • Configurator for '{template_name}' already exists")
		return frappe.get_doc("Style Attribute Configurator", existing)

	configurator = frappe.get_doc(
		{"doctype": "Style Attribute Configurator", "item_template": template_name, "item_attribute": "Color"}
	)

	configurator.insert(ignore_permissions=True)
	print(f"    ✓ Configurator created for '{template_name}'")
	return configurator


def create_style_variant(configurator_name, template_name, color, product_data):
	"""Create Style Attribute Variant for a specific color"""

	# Check if variant exists
	existing = frappe.db.get_value(
		"Style Attribute Variant", {"configurator": configurator_name, "attribute_value": color}, "name"
	)

	if existing:
		print(f"    • Style variant '{color}' already exists")
		return frappe.get_doc("Style Attribute Variant", existing)

	# Route should NOT include language prefix - hooks.py handles that
	route_slug = f"{product_data['code'].lower()}-{color.lower()}"

	color_hex_map = {
		"Black": "000000",
		"White": "FFFFFF",
		"Blue": "0000FF",
		"Red": "FF0000",
		"Green": "28A745",
		"Navy": "000080",
		"Gray": "6C757D",
	}

	bg_hex = color_hex_map.get(color, "6C757D")

	text_hex = "000000" if bg_hex == "FFFFFF" else "FFFFFF"

	image_text = f"{color} {product_data['name']}".replace(" ", "+")
	image_url = f"https://placehold.co/800x800/{bg_hex}/{text_hex}.png?text={image_text}"

	variant = frappe.get_doc(
		{
			"doctype": "Style Attribute Variant",
			"configurator": configurator_name,
			"item_style": template_name,
			"attribute_value": color,
			"attribute_name": "Color",
			"display_name": f"{product_data['name']} - {color}",
			"item_group": product_data["item_group"],
			"is_published": 1,
			"route": route_slug,
			"images": [
				{
					"image": image_url,
				}
			],
		}
	)

	variant.insert(ignore_permissions=True)
	print(f"    ✓ Style variant '{color}' created")
	return variant


def create_item_variants(template_name, product_data):
	"""Create actual item variants for all color/size combinations"""

	# warehouse = ensure_warehouse_exists()
	# company = frappe.defaults.get_user_default("Company") or frappe.db.get_value("Company", {}, "name")

	for color in product_data["colors"]:
		for size in product_data["sizes"]:
			variant_code = f"{product_data['code']}-{color[:3].upper()}-{size}"

			if frappe.db.exists("Item", variant_code):
				continue

			# Create variant item
			variant = frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": variant_code,
					"item_name": f"{product_data['name']} - {color} - {size}",
					"item_group": product_data["item_group"],
					"brand": product_data["brand"],
					"stock_uom": "Nos",
					"is_stock_item": 1,
					"variant_of": template_name,
					"description": product_data["description"],
					"custom_displayname": f"{product_data['name']} {color} {size}",
					"attributes": [
						{"attribute": "Color", "attribute_value": color},
						{"attribute": "Size", "attribute_value": size},
					],
					"opening_stock": random.randint(50, 200),
					"valuation_rate": product_data["base_price"] * 0.5,
				}
			)

			variant.insert(ignore_permissions=True)

			# Create item prices
			create_item_price(variant_code, "Standard Selling", product_data["base_price"])
			create_item_price(variant_code, "Sale Price List", product_data["sale_price"])

			# Link to Style Attribute Variant
			link_to_style_variant(template_name, color, size, variant_code)

	print(f"    ✓ All variants created for {template_name}")


def create_item_price(item_code, price_list, rate):
	"""Create item price"""
	if not frappe.db.exists("Item Price", {"item_code": item_code, "price_list": price_list}):
		price = frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": price_list,
				"price_list_rate": rate,
			}
		)
		price.insert(ignore_permissions=True)


def link_to_style_variant(template_name, color, size, variant_code):
	"""Link item variant to Style Attribute Variant"""

	# Get configurator
	configurator = frappe.db.get_value(
		"Style Attribute Configurator", {"item_template": template_name}, "name"
	)

	if not configurator:
		return

	# Get style variant
	style_variant = frappe.db.get_value(
		"Style Attribute Variant", {"configurator": configurator, "attribute_value": color}, "name"
	)

	if not style_variant:
		return

	# Update style variant with size mapping
	sv_doc = frappe.get_doc("Style Attribute Variant", style_variant)

	# Check if size already exists
	existing = False
	for row in sv_doc.sizes:
		if row.size == size:
			existing = True
			break

	if not existing:
		sv_doc.append("sizes", {"size": size, "item_code": variant_code})
		sv_doc.save(ignore_permissions=True)


def publish_style_variants():
	"""Ensure all Style Attribute Variants are published"""
	print("  - Publishing Style Attribute Variants...")

	savs = frappe.get_all("Style Attribute Variant", fields=["name", "display_name"])

	published = 0
	for sav in savs:
		# Check if it has Color Size Items
		has_sizes = frappe.db.exists("Color Size Item", {"parent": sav.name})

		if has_sizes:
			frappe.db.set_value("Style Attribute Variant", sav.name, "is_published", 1)
			published += 1

	print(f"    ✓ Published {published} Style Attribute Variants")


def create_website_items():
	"""Create and publish Website Items for all demo products"""
	print("  - Creating Website Items...")

	# Get all demo items (variants only, not templates)
	items = frappe.get_all(
		"Item",
		filters={
			"has_variants": 0,
			"is_stock_item": 1,
			"variant_of": ["in", ["BRAKE-PADS", "AIR-FILTER", "FLOOR-MATS"]],
		},
		fields=["name", "item_name", "item_group", "brand", "description", "variant_of"],
	)

	warehouse = ensure_warehouse_exists()

	count_created = 0
	count_published = 0

	for item in items:
		# Get full item details
		item_doc = frappe.get_doc("Item", item.name)

		# Check if Website Item already exists
		existing_wi = frappe.db.get_value("Website Item", {"item_code": item.name}, "name")

		if not existing_wi:
			# Get item group for website_item_groups
			item_groups = [item.item_group] if item.item_group else []

			# Create Website Item manually
			wi = frappe.get_doc(
				{
					"doctype": "Website Item",
					"item_code": item.name,
					"item_name": item.item_name,
					"web_item_name": item.item_name,
					"item_group": item.item_group,
					"brand": item.brand,
					"description": item.description or item_doc.description or "",
					"website_warehouse": warehouse,
					"published": 1,
					"website_item_groups": [{"item_group": ig} for ig in item_groups] if item_groups else [],
				}
			)
			wi.insert(ignore_permissions=True)
			count_created += 1
		else:
			# Publish and update existing Website Item
			wi_doc = frappe.get_doc("Website Item", existing_wi)
			wi_doc.published = 1
			wi_doc.website_warehouse = warehouse

			# Ensure website_item_groups is set
			if not wi_doc.website_item_groups and item.item_group:
				wi_doc.append("website_item_groups", {"item_group": item.item_group})

			wi_doc.save(ignore_permissions=True)
			count_published += 1

	print(f"    ✓ Created {count_created} Website Items")
	print(f"    ✓ Published {count_published} existing Website Items")


def fix_product_routes():
	"""Fix product routes - ensure clean slugs without prefixes"""
	print("  - Fixing product routes...")

	# Fix Style Attribute Variant routes
	savs = frappe.get_all(
		"Style Attribute Variant", fields=["name", "route", "attribute_value", "item_style"]
	)
	sav_count = 0

	for sav in savs:
		# Get template code for route generation
		template_code = frappe.db.get_value("Item", sav.item_style, "item_code")
		if template_code:
			# Generate clean slug: template-color
			clean_route = f"{template_code.lower()}-{sav.attribute_value.lower()}".replace("_", "-").replace(
				" ", "-"
			)

			# Update if different
			if sav.route != clean_route:
				frappe.db.set_value("Style Attribute Variant", sav.name, "route", clean_route)
				sav_count += 1

	# Website Item ships with webshop, which this app does not depend on; absent, there are no rows.
	website_items = (
		frappe.get_all("Website Item", fields=["name", "item_code", "route"])
		if frappe.db.exists("DocType", "Website Item")
		else []
	)
	wi_count = 0

	for wi in website_items:
		# Generate clean slug from item code
		clean_route = wi.item_code.lower().replace("_", "-").replace(" ", "-")

		# Remove any existing prefix if present
		if wi.route and ("en/products/" in wi.route or "ar/products/" in wi.route):
			clean_route = wi.route.replace("en/products/", "").replace("ar/products/", "")

		# Update if needed
		if wi.route != clean_route:
			frappe.db.set_value("Website Item", wi.name, "route", clean_route)
			wi_count += 1

	print(f"    ✓ Fixed {sav_count} SAV routes")
	print(f"    ✓ Fixed {wi_count} Website Item routes")
	print("    Note: Routes are clean slugs - hooks.py adds /en/products/ prefix")


def create_ecommerce_group():
	"""Create Ecommerce Website parent and car parts category item groups"""
	parent = "Ecommerce Website"

	# Car parts categories (matching Ecommerce Category doctype)
	parent_categories = {
		"Engine Parts": "Engine Parts",
		"Brake System": "Brake System",
		"Interior Accessories": "Interior Accessories",
	}

	# Find or create root item group
	root_item_group = get_root_item_group()

	# Create parent group
	frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": parent,
			"is_group": True,
			"parent_item_group": root_item_group,
			"custom_displayname": parent,
		}
	).insert(ignore_if_duplicate=True)

	# Create car parts category item groups
	for category_name, display_name in parent_categories.items():
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": category_name,
				"is_group": True,
				"parent_item_group": parent,
				"custom_displayname": display_name,
			}
		).insert(ignore_if_duplicate=True)


def get_root_item_group():
	"""Find or create the root item group"""
	# Try to find existing root item group (parent_item_group is null)
	root_groups = frappe.get_all(
		"Item Group", filters={"parent_item_group": ["in", ["", None]]}, fields=["name"], limit=1
	)

	if root_groups:
		return root_groups[0].name

	# If no root exists, create "All Item Groups"
	root_name = "All Item Groups"
	if not frappe.db.exists("Item Group", root_name):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": root_name,
				"is_group": True,
				"parent_item_group": "",
				"custom_displayname": root_name,
			}
		).insert(ignore_permissions=True)

	return root_name


def create_ecommerce_categories():
	"""Create default Ecommerce Categories (now database-driven instead of hardcoded)"""

	categories = [
		{
			"category_name": "Engine Parts",
			"display_name": "Engine Parts",
			"route_slug": "engine-parts",
			"link_type": "Item Group",
			"item_group": "Engine Parts",
			"enabled": 1,
			"display_order": 1,
		},
		{
			"category_name": "Brake System",
			"display_name": "Brake System",
			"route_slug": "brake-system",
			"link_type": "Item Group",
			"item_group": "Brake System",
			"enabled": 1,
			"display_order": 2,
		},
		{
			"category_name": "Interior Accessories",
			"display_name": "Interior Accessories",
			"route_slug": "interior-accessories",
			"link_type": "Item Group",
			"item_group": "Interior Accessories",
			"enabled": 1,
			"display_order": 3,
		},
	]

	for cat_data in categories:
		if not frappe.db.exists("Ecommerce Category", cat_data["category_name"]):
			cat = frappe.get_doc({"doctype": "Ecommerce Category", **cat_data})
			cat.insert(ignore_permissions=True)
			frappe.errprint(f"Created Ecommerce Category: {cat_data['category_name']}")
		else:
			frappe.errprint(f"Ecommerce Category '{cat_data['category_name']}' already exists")


def create_default_footer_sections():
	"""Create default footer sections in Commera Settings"""

	if not frappe.db.exists("Commera Settings", "Commera Settings"):
		frappe.errprint("Commera Settings not found, skipping footer sections")
		return

	settings = frappe.get_doc("Commera Settings", "Commera Settings")

	# Set default email templates if not already set (required fields)
	if not settings.order_confirmation_email_template:
		settings.order_confirmation_email_template = "Order Confirmation"

	if not settings.item_in_stock_email_template:
		settings.item_in_stock_email_template = "Item In Stock"

	if not settings.order_cancellation_email_template:
		settings.order_cancellation_email_template = "Order Cancellation"

	# Only create if no footer sections exist
	if settings.footer_sections:
		frappe.errprint("Footer sections already exist, skipping")
		return

	# Default footer sections with common e-commerce links
	default_sections = [
		{
			"section_title": "My Account",
			"section_order": 1,
			"enabled": 1,
			"footer_links": [
				{"link_label": "My Account", "link_url": "/account/dashboard", "link_order": 1, "enabled": 1},
				{
					"link_label": "Orders History",
					"link_url": "/account/orders",
					"link_order": 2,
					"enabled": 1,
				},
				{"link_label": "Wishlist", "link_url": "/account/wishlist", "link_order": 3, "enabled": 1},
				{"link_label": "Track Order", "link_url": "#", "link_order": 4, "enabled": 1},
			],
		},
		{
			"section_title": "Policies",
			"section_order": 2,
			"enabled": 1,
			"footer_links": [
				{"link_label": "Privacy Policy", "link_url": "#", "link_order": 1, "enabled": 1},
				{"link_label": "Terms and Conditions", "link_url": "#", "link_order": 2, "enabled": 1},
				{"link_label": "Shipping Policy", "link_url": "#", "link_order": 3, "enabled": 1},
				{"link_label": "Returns Policy", "link_url": "#", "link_order": 4, "enabled": 1},
				{"link_label": "Payment Policy", "link_url": "#", "link_order": 5, "enabled": 1},
			],
		},
		{
			"section_title": "Customer Service",
			"section_order": 3,
			"enabled": 1,
			"footer_links": [
				{"link_label": "FAQ", "link_url": "#", "link_order": 1, "enabled": 1},
				{"link_label": "Contact Us", "link_url": "#", "link_order": 2, "enabled": 1},
				{"link_label": "Sizing Charts", "link_url": "#", "link_order": 3, "enabled": 1},
				{"link_label": "International Shipping", "link_url": "#", "link_order": 4, "enabled": 1},
			],
		},
	]

	# Create Footer Section Config records and link them to Commera Settings
	for section_data in default_sections:
		# Create Footer Section Config
		section_config_name = section_data["section_title"]
		if not frappe.db.exists("Footer Section Config", section_config_name):
			section_config = frappe.get_doc(
				{
					"doctype": "Footer Section Config",
					"section_title": section_config_name,
					"section_order": section_data["section_order"],
					"enabled": section_data["enabled"],
					"footer_links": section_data["footer_links"],
				}
			)
			section_config.insert(ignore_permissions=True)
			frappe.errprint(f"Created Footer Section Config: {section_config_name}")

		# Add to Commera Settings footer_sections (Footer Section Mapping)
		settings.append(
			"footer_sections",
			{
				"footer_section": section_config_name,
				"section_order": section_data["section_order"],
				"enabled": section_data["enabled"],
			},
		)

	settings.save(ignore_permissions=True)
	frappe.errprint("✅ Default footer sections created")


if __name__ == "__main__":
	install_demo_data()
