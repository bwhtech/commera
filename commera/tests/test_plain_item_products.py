import frappe
from erpnext.controllers.item_variant import create_variant
from frappe.utils import getdate

from commera.api.admin.catalog import (
	DEFAULT_OPTION_ATTRIBUTE,
	DEFAULT_OPTION_VALUE,
	DEFAULT_SIZE_VALUE,
	ensure_attribute_exists,
	get_product,
	get_products,
	save_product_options,
)
from commera.api.variant_pricing import get_size_item_codes, set_variant_prices
from commera.sdk.catalog import get_product_cards_for
from commera.tests.test_admin_orders import COMPANY, CURRENCY, ensure_fiscal_year
from commera.tests.test_product_onboarding import ProductOnboardingTestCase
from commera.www.account.orders.index import get_orders_list
from commera.www.cart.checkout import get_checkout_items


class TestPlainItemProducts(ProductOnboardingTestCase):
	def setUp(self):
		super().setUp()
		ensure_attribute_exists(DEFAULT_OPTION_ATTRIBUTE, DEFAULT_OPTION_VALUE, "STD")
		self.plain_item = self.make_plain_item()
		self.plain_variant = self.wrap_item(
			self.plain_item,
			DEFAULT_OPTION_ATTRIBUTE,
			DEFAULT_OPTION_VALUE,
			{DEFAULT_SIZE_VALUE: self.plain_item},
		)

	def wrap_item(self, item_template, option_attribute, option_value, sizes_by_label):
		configurator = frappe.new_doc("Style Attribute Configurator")
		configurator.item_template = item_template
		configurator.item_attribute = option_attribute
		configurator.flags.skip_variant_generation = True
		configurator.insert()

		variant = frappe.new_doc("Style Attribute Variant")
		variant.configurator = configurator.name
		variant.item_style = item_template
		variant.attribute_value = option_value
		variant.display_name = frappe.db.get_value("Item", item_template, "item_name")
		for label, item_code in sizes_by_label.items():
			variant.append("sizes", {"size": label, "item_code": item_code})
		variant.insert()
		return variant

	def make_quotation(self, item_code):
		quotation = frappe.new_doc("Quotation")
		quotation.quotation_to = "Customer"
		quotation.party_name = self.make_customer()
		quotation.company = COMPANY
		quotation.currency = CURRENCY
		quotation.conversion_rate = 1
		quotation.append("items", {"item_code": item_code, "qty": 1, "rate": 499})
		quotation.flags.ignore_permissions = True
		quotation.insert()
		return quotation

	def make_sales_order(self, item_code):
		ensure_fiscal_year()
		sales_order = frappe.new_doc("Sales Order")
		sales_order.customer = self.make_customer()
		sales_order.company = COMPANY
		sales_order.currency = CURRENCY
		sales_order.conversion_rate = 1
		sales_order.transaction_date = getdate()
		sales_order.delivery_date = getdate()
		sales_order.append(
			"items", {"item_code": item_code, "qty": 1, "rate": 499, "warehouse": self.warehouse}
		)
		sales_order.flags.ignore_permissions = True
		sales_order.insert()
		return sales_order.name

	def make_customer(self):
		customer = frappe.new_doc("Customer")
		customer.customer_name = f"Plain Item Shopper {frappe.generate_hash(length=8)}"
		customer.customer_type = "Individual"
		customer.insert(ignore_permissions=True)
		return customer.name

	def test_products_list_shows_the_plain_item_with_price_and_stock(self):
		set_variant_prices(self.plain_item, default_rate=499)
		self.plain_variant.receive_stock({self.plain_item: 4}, {self.plain_item: 100})

		listed = {row["name"]: row for row in get_products(search=self.plain_item)["products"]}

		product = listed[self.plain_item]
		self.assertEqual((product["price_from"], product["price_to"], product["stock"]), (499, 499, 4))

	def test_the_product_card_has_no_colour_for_the_standard_option(self):
		set_variant_prices(self.plain_item, default_rate=499)
		self.plain_variant.receive_stock({self.plain_item: 4}, {self.plain_item: 100})
		self.plain_variant.db_set("is_published", 1)

		(card,) = get_product_cards_for([self.plain_variant.name])

		self.assertIsNone(card["color"])

	def test_price_editing_finds_the_plain_item_itself(self):
		self.assertEqual(get_size_item_codes(self.plain_item), [self.plain_item])

		set_variant_prices(self.plain_item, default_rate=250, sale_rate=200)

		self.assertEqual(self.get_price(self.plain_item, self.default_price_list), 250)
		self.assertEqual(self.get_price(self.plain_item, self.sale_price_list), 200)

	def test_checkout_lists_the_plain_item_as_one_size(self):
		lines = get_checkout_items(self.make_quotation(self.plain_item))

		self.assertEqual(
			[(line.item_code, line.size) for line in lines], [(self.plain_item, DEFAULT_SIZE_VALUE)]
		)

	def test_checkout_lists_a_template_without_a_size_attribute_by_its_label(self):
		material = frappe.new_doc("Item Attribute")
		material.attribute_name = f"Plain Material {self.suffix}"
		material.append("item_attribute_values", {"attribute_value": "Cotton", "abbr": "COT"})
		material.insert()
		item_template = self.make_item_template_with(material.name)
		cotton_item = create_variant(item_template, {material.name: "Cotton"})
		cotton_item.insert()
		self.wrap_item(item_template, material.name, "Cotton", {DEFAULT_SIZE_VALUE: cotton_item.name})

		lines = get_checkout_items(self.make_quotation(cotton_item.name))

		self.assertEqual(
			[(line.item_code, line.size) for line in lines], [(cotton_item.name, DEFAULT_SIZE_VALUE)]
		)

	def test_order_page_shows_the_plain_item_line(self):
		sales_order = self.make_sales_order(self.plain_item)

		_total, orders = get_orders_list([sales_order], owned_only=False)

		lines = frappe.parse_json(orders[0]["items"])
		self.assertEqual(
			[(line["item_code"], line["size"]) for line in lines], [(self.plain_item, DEFAULT_SIZE_VALUE)]
		)

	def test_order_page_hides_an_order_of_items_that_are_not_store_products(self):
		sales_order = self.make_sales_order(self.make_plain_item())

		_total, orders = get_orders_list([sales_order], owned_only=False)

		self.assertEqual(orders, [])

	def test_a_size_variant_keeps_its_size_attribute_on_the_order_page(self):
		sales_order = self.make_sales_order(self.size_item_codes[0])

		_total, orders = get_orders_list([sales_order], owned_only=False)

		self.assertEqual([line["size"] for line in frappe.parse_json(orders[0]["items"])], ["S"])

	def test_a_plain_item_offers_no_options_to_edit(self):
		self.assertFalse(get_product(self.plain_item)["can_edit_options"])

	def test_editing_options_of_a_plain_item_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "without variants"):
			save_product_options(self.plain_item, add=[[DEFAULT_OPTION_VALUE, "Large"]])

	def test_a_plain_product_keeps_its_collections_in_step(self):
		other_group = self.make_item_group_named(f"Plain Other {self.suffix}")
		item = frappe.get_doc("Item", self.plain_item)
		item.set("custom_collections", [{"item_group": other_group}, {"item_group": self.item_group}])
		item.save()

		self.assertEqual(frappe.db.get_value("Item", self.plain_item, "item_group"), other_group)

	def make_item_template_with(self, attribute):
		item = frappe.new_doc("Item")
		item.item_code = f"PLAIN-TEMPLATE-{frappe.generate_hash(length=8).upper()}"
		item.item_name = item.item_code
		item.item_group = self.item_group
		item.stock_uom = "Nos"
		item.has_variants = 1
		item.variant_based_on = "Item Attribute"
		item.append("attributes", {"attribute": attribute})
		item.insert()
		return item.name

	def make_item_group_named(self, name):
		item_group = frappe.new_doc("Item Group")
		item_group.item_group_name = name
		item_group.parent_item_group = "All Item Groups"
		item_group.custom_displayname = name
		item_group.insert()
		return item_group.name
