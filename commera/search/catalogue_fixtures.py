"""The search test catalogue: a style with red, blue and green variants, shared by every engine's tests."""

import frappe

SEARCH_TOKEN = "zzwidget"
ARABIC_TERM = "قميص"
SHORT_TERM = "abc"

# Deliberately not title-stable: the sidebar used to title-case values, which the BINARY index missed.
BRAND = "ZZ TestSearch Brand"
ITEM_GROUP = "ZZ Test Search Group"
# A second group so the facet cross-filter tests have two variants that differ on a facet column.
ITEM_GROUP_BLUE = "ZZ Test Search Group Blue"
STYLE_ITEM = "ZZ-TEST-STYLE"
ITEM_ATTRIBUTE = "Zz Test Color"
CATEGORY_NAME = "Zz Test Category"
NON_PRIVILEGED_USER = "zz_test_search_user@example.com"


class SearchCatalogue:
	"""Class-level fixtures. Callers commit them, because they outlive one test method."""

	@classmethod
	def drop_catalogue(cls):
		"""Remove any fixtures left behind by an aborted run so setUpClass is re-runnable."""
		for doctype, filters in (
			("Item Price", {"item_code": ("like", "ZZ-%")}),
			("Style Attribute Variant", {"item_style": STYLE_ITEM}),
			("Style Attribute Configurator", {"item_template": STYLE_ITEM}),
			("Ecommerce Category", {"category_name": CATEGORY_NAME}),
			("Item", {"item_group": ITEM_GROUP}),
			("Item Group", {"name": ("in", [ITEM_GROUP, ITEM_GROUP_BLUE])}),
			("Item Attribute", {"name": ITEM_ATTRIBUTE}),
			("Brand", {"name": BRAND}),
		):
			for name in frappe.get_all(doctype, filters=filters, pluck="name"):
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)

	def unpublish(self, variant_name):
		"""Unpublish a variant for the duration of one test, restoring it afterwards."""
		frappe.db.set_value("Style Attribute Variant", variant_name, "is_published", 0)
		self.addCleanup(frappe.db.set_value, "Style Attribute Variant", variant_name, "is_published", 1)

	@classmethod
	def build_catalogue(cls):
		cls.ensure_item_group()
		cls.ensure_brand()
		cls.ensure_item_attribute()
		cls.ensure_item(STYLE_ITEM, "Zzwidget Style Template", brand=BRAND)

		configurator = frappe.get_doc(
			{
				"doctype": "Style Attribute Configurator",
				"item_template": STYLE_ITEM,
				"item_attribute": ITEM_ATTRIBUTE,
			}
		).insert(ignore_permissions=True)

		# red: discounted + cheapest; blue: pricier, no discount. They differ on item_group AND size for the
		# facet cross-filter assertions. Numeric sizes, where the sidebar can order 10 before 8.
		cls.red = cls.make_variant(
			configurator.name,
			color="Zzred",
			display_name="Zzwidget Premium Red",
			sizes=[("8", "ZZ-RED-S", 100, 80), ("10", "ZZ-RED-M", 120, 90)],
		)
		cls.blue = cls.make_variant(
			configurator.name,
			color="Zzblue",
			display_name="Zzwidget Premium Blue",
			sizes=[("38", "ZZ-BLUE-S", 200, None), ("40", "ZZ-BLUE-M", 220, None)],
			item_group=ITEM_GROUP_BLUE,
		)
		# green: published but deliberately outside the index scope, to prove it never leaks into FTS results.
		cls.green = cls.make_variant(
			configurator.name,
			color="Zzgreen",
			display_name="Zzwidget Premium Green",
			sizes=[("ZS", "ZZ-GREEN-S", 150, None)],
		)
		cls.category = (
			frappe.get_doc(
				{
					"doctype": "Ecommerce Category",
					"category_name": CATEGORY_NAME,
					"display_name": "Zzwidget Test Category",
					"route_slug": "zz-test-category",
					"enabled": 1,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	@classmethod
	def make_variant(cls, configurator, color, display_name, sizes, item_group=ITEM_GROUP):
		"""Create one published Style Attribute Variant + its size SKUs + Item Prices."""
		for _label, item_code, default_rate, sale_rate in sizes:
			cls.ensure_item(item_code, f"{display_name} {item_code}")
			cls.make_price(item_code, cls.default_price_list, default_rate)
			if sale_rate is not None:
				cls.make_price(item_code, cls.sale_price_list, sale_rate)

		variant = frappe.get_doc(
			{
				"doctype": "Style Attribute Variant",
				"configurator": configurator,
				"item_style": STYLE_ITEM,
				"attribute_value": color,
				"attribute_name": "Color",
				"display_name": display_name,
				"item_group": item_group,
				"is_published": 1,
				"images": [{"image": "/files/zz-a.png"}, {"image": "/files/zz-b.png"}],
				"sizes": [{"size": label, "item_code": item_code} for label, item_code, _d, _s in sizes],
			}
		).insert(ignore_permissions=True)
		return variant.name

	@classmethod
	def make_price(cls, item_code, price_list, rate):
		price = frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": price_list,
				"price_list_rate": rate,
			}
		).insert(ignore_permissions=True)
		cls.price_names[(item_code, price_list)] = price.name

	@classmethod
	def ensure_item(cls, item_code, item_name, brand=None):
		if frappe.db.exists("Item", item_code):
			return
		doc = {
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_name,
			"item_group": ITEM_GROUP,
			"stock_uom": "Nos",
			"is_stock_item": 1,
		}
		if brand:
			doc["brand"] = brand
		frappe.get_doc(doc).insert(ignore_permissions=True)

	@classmethod
	def ensure_item_group(cls):
		for item_group in (ITEM_GROUP, ITEM_GROUP_BLUE):
			if frappe.db.exists("Item Group", item_group):
				continue
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": item_group,
					"is_group": 0,
					"parent_item_group": "All Item Groups",
					# commera customises Item Group with two mandatory storefront display names.
					"custom_displayname": item_group,
				}
			).insert(ignore_permissions=True)

	@classmethod
	def ensure_brand(cls):
		if not frappe.db.exists("Brand", BRAND):
			frappe.get_doc({"doctype": "Brand", "brand": BRAND}).insert(ignore_permissions=True)

	@classmethod
	def ensure_item_attribute(cls):
		if not frappe.db.exists("Item Attribute", ITEM_ATTRIBUTE):
			frappe.get_doc(
				{
					"doctype": "Item Attribute",
					"attribute_name": ITEM_ATTRIBUTE,
					"item_attribute_values": [{"attribute_value": "Zzred", "abbr": "ZZR"}],
				}
			).insert(ignore_permissions=True)

	@classmethod
	def ensure_non_privileged_user(cls):
		"""A User with no System Manager role, to prove the rebuild endpoint rejects low-privilege callers."""
		if not frappe.db.exists("User", NON_PRIVILEGED_USER):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": NON_PRIVILEGED_USER,
					"first_name": "Zz Test Search User",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
