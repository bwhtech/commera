# Copyright (c) 2026, company@bwhstudios.com and Contributors

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from commera.api.admin.catalog import get_option_suggestions, get_product_types
from commera.data.product_taxonomy import PRODUCT_TAXONOMY

STORE_CATEGORIES = {"Fashion", "Beauty", "Home", "Food", "Electronics"}


def get_product_type_rows():
	return [
		(category, group, product_type, attributes)
		for category, groups in PRODUCT_TAXONOMY.items()
		for group, product_types in groups.items()
		for product_type, attributes in product_types.items()
	]


class TestProductTaxonomyData(UnitTestCase):
	def test_every_type_sits_under_a_store_category(self):
		self.assertEqual(set(PRODUCT_TAXONOMY), STORE_CATEGORIES)
		for category in STORE_CATEGORIES:
			with self.subTest(category=category):
				self.assertTrue(PRODUCT_TAXONOMY[category])

	def test_every_product_type_name_is_unique(self):
		product_types = [row[2] for row in get_product_type_rows()]

		self.assertEqual(len(product_types), len(set(product_types)))
		self.assertGreaterEqual(len(product_types), 100)

	def test_every_suggested_attribute_has_distinct_values(self):
		for category, group, product_type, attributes in get_product_type_rows():
			with self.subTest(category=category, group=group, product_type=product_type):
				self.assertTrue(attributes)
				for attribute, values in attributes.items():
					self.assertTrue(attribute.strip())
					self.assertTrue(values, attribute)
					self.assertTrue(all(value.strip() for value in values), attribute)
					self.assertEqual(len(values), len({value.casefold() for value in values}), attribute)


class TestOptionSuggestions(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_category_lists_its_types_by_group(self):
		groups = {row["group"]: row["product_types"] for row in get_product_types("Fashion")}

		self.assertIn("Dresses", groups["Clothing"])
		self.assertIn("Sneakers", groups["Shoes"])
		self.assertEqual(get_product_types("Not a category"), [])

	def test_a_type_suggests_its_attributes_with_values(self):
		suggestions = {row["name"]: row["values"] for row in get_option_suggestions("Dresses")}

		self.assertEqual(list(suggestions), ["Color", "Size", "Material", "Sleeve"])
		self.assertIn("M", suggestions["Size"])
		self.assertIn("Cotton", suggestions["Material"])
		self.assertEqual(get_option_suggestions("Not a type"), [])

	def test_changing_a_suggestion_leaves_the_taxonomy_alone(self):
		get_option_suggestions("Dresses")[0]["values"].append("Zz Not A Color")

		self.assertNotIn("Zz Not A Color", get_option_suggestions("Dresses")[0]["values"])

	def test_a_guest_cannot_read_suggestions(self):
		frappe.set_user("Guest")

		with self.assertRaises(frappe.PermissionError):
			get_option_suggestions("Dresses")
		with self.assertRaises(frappe.PermissionError):
			get_product_types("Fashion")
