# Copyright (c) 2026, company@bwhstudios.com and Contributors

import frappe
from erpnext.controllers.item_variant import create_variant

from commera.api.admin.catalog import SIZE_ATTRIBUTE
from commera.patches import add_size_option_values
from commera.tests.test_admin_catalog import DeleteProductTestCase


class TestVariantOptionValues(DeleteProductTestCase):
	def get_pages(self, item_template):
		configurator = frappe.db.get_value("Style Attribute Configurator", {"item_template": item_template})
		return frappe.get_all("Style Attribute Variant", filters={"configurator": configurator}, pluck="name")

	def get_option_values(self, item_template):
		return frappe.get_all(
			"Variant Option Value",
			filters={
				"parenttype": "Style Attribute Variant",
				"parent": ["in", self.get_pages(item_template)],
			},
			fields=["item_code", "attribute", "value", "position"],
			order_by="item_code asc, position asc",
		)

	def get_sizes(self, item_template):
		return frappe.get_all(
			"Color Size Item",
			filters={
				"parenttype": "Style Attribute Variant",
				"parent": ["in", self.get_pages(item_template)],
			},
			fields=["item_code", "size"],
			order_by="item_code asc",
		)

	def get_size_options(self, item_template):
		return [
			{"item_code": row.item_code, "attribute": SIZE_ATTRIBUTE, "value": row.size, "position": 2}
			for row in self.get_sizes(item_template)
		]

	def add_size_values(self, values):
		size = frappe.get_doc("Item Attribute", SIZE_ATTRIBUTE)
		listed = {row.attribute_value for row in size.item_attribute_values}
		for value in values:
			if value not in listed:
				size.append(
					"item_attribute_values", {"attribute_value": value, "abbr": f"{value}{self.suffix}"}
				)
		size.save()

	def add_product_with_attributes(self, attribute_values):
		item_template = frappe.new_doc("Item")
		item_template.item_code = f"Option Values {frappe.generate_hash(length=6).upper()}"
		item_template.item_name = item_template.item_code
		item_template.item_group = self.item_group
		item_template.stock_uom = "Nos"
		item_template.has_variants = 1
		item_template.variant_based_on = "Item Attribute"
		for attribute in attribute_values:
			item_template.append("attributes", {"attribute": attribute})
		item_template.insert()

		for size in attribute_values[SIZE_ATTRIBUTE]:
			values = {attribute: values[0] for attribute, values in attribute_values.items()}
			values[SIZE_ATTRIBUTE] = size
			create_variant(item_template.name, values).insert()

		configurator = frappe.new_doc("Style Attribute Configurator")
		configurator.item_template = item_template.name
		configurator.item_attribute = self.colour_attribute
		configurator.flags.skip_variant_generation = True
		configurator.insert()
		configurator.generate_variants()
		return item_template.name

	def test_each_variant_gets_its_size_as_an_option_value(self):
		item_template = self.add_product()

		self.assertEqual(len(self.get_sizes(item_template)), 2)
		self.assertEqual(self.get_option_values(item_template), self.get_size_options(item_template))

	def test_a_third_attribute_takes_the_position_after_size(self):
		self.add_size_values(["S", "M"])
		material = self.make_named_attribute("Material", ["Cotton"])
		item_template = self.add_product_with_attributes(
			{self.colour_attribute: ["Crimson"], SIZE_ATTRIBUTE: ["S", "M"], material: ["Cotton"]}
		)

		option_values = self.get_option_values(item_template)
		self.assertEqual(len(option_values), 4)
		for item_code, size in {row.item_code: row.size for row in self.get_sizes(item_template)}.items():
			self.assertEqual(
				[
					(row.attribute, row.value, row.position)
					for row in option_values
					if row.item_code == item_code
				],
				[(SIZE_ATTRIBUTE, size, 2), (material, "Cotton", 3)],
			)

	def test_a_fourth_option_is_refused(self):
		self.add_size_values(["S"])
		material = self.make_named_attribute("Material", ["Cotton"])
		fit = self.make_named_attribute("Fit", ["Slim"])

		with self.assertRaisesRegex(frappe.ValidationError, "at most 3 options"):
			self.add_product_with_attributes(
				{
					self.colour_attribute: ["Crimson"],
					SIZE_ATTRIBUTE: ["S"],
					material: ["Cotton"],
					fit: ["Slim"],
				}
			)

	def test_the_patch_backfills_sizes_once(self):
		item_template = self.add_product()
		frappe.db.delete(
			"Variant Option Value",
			{"parenttype": "Style Attribute Variant", "parent": ["in", self.get_pages(item_template)]},
		)

		add_size_option_values.execute()
		add_size_option_values.execute()

		self.assertEqual(self.get_option_values(item_template), self.get_size_options(item_template))
