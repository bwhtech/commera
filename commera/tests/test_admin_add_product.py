# Copyright (c) 2026, company@bwhstudios.com and Contributors
# Tests for what the Add product dialog reads and sends: the size-only product, the collection and
# option pickers, and the duplicate-title refusal it shows on the Title field.

import frappe

from commera.api.admin.catalog import (
	DEFAULT_OPTION_ATTRIBUTE,
	DEFAULT_OPTION_VALUE,
	DEFAULT_SIZE_VALUE,
	SIZE_ATTRIBUTE,
	create_product,
	ensure_attribute_exists,
	get_attribute_values,
	get_attributes,
	get_collections,
	get_default_collection,
	get_product,
	get_seeded_item_groups,
)
from commera.tests.test_product_onboarding import ProductOnboardingTestCase


class TestAddProduct(ProductOnboardingTestCase):
	def add_product(self, **kwargs):
		kwargs.setdefault("title", f"Add Product {frappe.generate_hash(length=6).upper()}")
		kwargs.setdefault("collection", self.item_group)
		return create_product(**kwargs)["name"]

	def get_sizes_by_option(self, item_template):
		return {
			variant["option"]: sorted(size["size"] for size in variant["sizes"])
			for variant in get_product(item_template)["variants"]
		}

	def test_sizes_with_no_colour_become_one_variant_each(self):
		for option_sizes in (
			[{"option": DEFAULT_OPTION_VALUE, "sizes": ["S", "M", "L"]}],
			[{"option": "", "sizes": ["S", "M", "L"]}],
		):
			item_template = self.add_product(option_attribute="Color", option_sizes=option_sizes)

			self.assertEqual(self.get_sizes_by_option(item_template), {DEFAULT_OPTION_VALUE: ["L", "M", "S"]})
			self.assertEqual(frappe.db.count("Item", {"variant_of": item_template}), 3)
			self.assertEqual(
				frappe.db.get_value(
					"Style Attribute Configurator", {"item_template": item_template}, "item_attribute"
				),
				DEFAULT_OPTION_ATTRIBUTE,
			)

	def test_a_sized_row_without_a_colour_beside_named_colours_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.add_product(
				option_attribute=self.attribute,
				option_sizes=[{"option": "Red", "sizes": ["S"]}, {"option": "", "sizes": ["M"]}],
			)

	def test_a_taken_title_is_a_duplicate_entry(self):
		title = f"Add Product {frappe.generate_hash(length=6).upper()}"
		self.add_product(title=title)

		with self.assertRaises(frappe.DuplicateEntryError):
			self.add_product(title=title)

	def test_the_picker_hides_the_collections_erpnext_seeds(self):
		seeded = get_seeded_item_groups()
		self.assertIn("Raw Material", seeded)
		self.assertIn("Products", seeded)

		offered = get_collections()
		self.assertIn(self.item_group, offered)
		self.assertFalse(set(seeded) & set(offered))

	def test_the_last_used_collection_is_preselected(self):
		other_collection = self.make_item_group_named(f"Add Product Other {self.suffix}")
		self.assertEqual(get_default_collection(), self.item_group)

		self.add_product(collection=other_collection)
		self.assertEqual(get_default_collection(), other_collection)

	def make_item_group_named(self, name):
		item_group = frappe.new_doc("Item Group")
		item_group.item_group_name = name
		item_group.parent_item_group = "All Item Groups"
		item_group.custom_displayname = name
		item_group.insert()
		return item_group.name

	def test_size_and_the_placeholder_are_not_option_axes(self):
		# Made here, not assumed: in CI's test order nothing may have created Color or Size yet.
		ensure_attribute_exists("Color", "Red", "RED")
		ensure_attribute_exists(SIZE_ATTRIBUTE, DEFAULT_SIZE_VALUE, "OS")
		options = {row["name"]: row["is_option"] for row in get_attributes()}

		self.assertTrue(options["Color"])
		self.assertTrue(options[self.attribute])
		self.assertFalse(options["Size"])
		if DEFAULT_OPTION_ATTRIBUTE in options:
			self.assertFalse(options[DEFAULT_OPTION_ATTRIBUTE])

	def test_the_pickers_never_offer_the_placeholder_values(self):
		# A product with no options makes the Title/Standard and Size/One Size values it sells on.
		self.add_product()
		self.add_product(option_attribute="Color", option_sizes=[{"option": "", "sizes": ["S"]}])
		self.assertTrue(
			frappe.db.exists(
				"Item Attribute Value", {"parent": SIZE_ATTRIBUTE, "attribute_value": DEFAULT_SIZE_VALUE}
			)
		)

		offered_sizes = [row["value"] for row in get_attribute_values(SIZE_ATTRIBUTE)]
		self.assertIn("S", offered_sizes)
		self.assertNotIn(DEFAULT_SIZE_VALUE, offered_sizes)
		self.assertNotIn(
			DEFAULT_OPTION_VALUE, [row["value"] for row in get_attribute_values(DEFAULT_OPTION_ATTRIBUTE)]
		)

		values = {row["name"]: [value["value"] for value in row["values"]] for row in get_attributes()}
		self.assertNotIn(DEFAULT_SIZE_VALUE, values[SIZE_ATTRIBUTE])
		self.assertNotIn(DEFAULT_OPTION_VALUE, values.get(DEFAULT_OPTION_ATTRIBUTE, []))
