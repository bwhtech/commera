# Copyright (c) 2026, company@bwhstudios.com and Contributors

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin.catalog import (
	DEFAULT_OPTION_ATTRIBUTE,
	DEFAULT_OPTION_VALUE,
	ensure_attribute_exists,
	get_attribute_values,
	get_attributes,
	get_picker_values,
)
from commera.data.store_options import CATEGORY_OPTIONS, EVERY_STORE_OPTIONS
from commera.store_options import add_store_options, append_attribute_values
from commera.swatches import CACHE_KEY

FASHION_ATTRIBUTES = ["Color", "Size", "Material", "Fit", "Sleeve"]
TEST_SIZE = "Zz Store Options Size"
TEST_SAVEPOINT = "store_options_test"


def get_values_by_attribute(attribute_names):
	rows = frappe.get_all(
		"Item Attribute Value",
		filters={"parent": ["in", attribute_names], "parenttype": "Item Attribute"},
		fields=["parent", "attribute_value", "abbr"],
		order_by="idx asc",
	)
	values_by_attribute = {}
	for row in rows:
		values_by_attribute.setdefault(row.parent, {})[row.attribute_value] = row.abbr
	return values_by_attribute


def make_attribute(name, values_with_abbreviations):
	attribute = frappe.new_doc("Item Attribute")
	attribute.attribute_name = name
	for value, abbreviation in values_with_abbreviations:
		attribute.append("item_attribute_values", {"attribute_value": value, "abbr": abbreviation})
	attribute.insert()
	return attribute


class TestStoreOptions(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint(TEST_SAVEPOINT)

	def tearDown(self):
		frappe.db.rollback(save_point=TEST_SAVEPOINT)
		frappe.cache.delete_value(CACHE_KEY)

	def test_fashion_store_gets_its_options_and_every_store_set(self):
		add_store_options("Fashion")

		values_by_attribute = get_values_by_attribute(FASHION_ATTRIBUTES)
		expected = EVERY_STORE_OPTIONS | CATEGORY_OPTIONS["Fashion"]
		for attribute, values in expected.items():
			self.assertLessEqual(set(values), set(values_by_attribute[attribute]), attribute)
		self.assertFalse(frappe.db.exists("Item Attribute", "Shade"))

	def test_running_twice_creates_no_duplicates(self):
		add_store_options("Fashion")
		first = get_values_by_attribute(FASHION_ATTRIBUTES)
		attribute_count = frappe.db.count("Item Attribute")

		add_store_options("Fashion")

		self.assertEqual(get_values_by_attribute(FASHION_ATTRIBUTES), first)
		self.assertEqual(frappe.db.count("Item Attribute"), attribute_count)

	def test_existing_attribute_only_gains_missing_values(self):
		if frappe.db.exists("Item Attribute", "Fit"):
			frappe.delete_doc("Item Attribute", "Fit", force=True)
		make_attribute("Fit", [("slim", "SL"), ("Tailored", "TAILORED")])

		add_store_options("Fashion")

		fit_values = get_values_by_attribute(["Fit"])["Fit"]
		self.assertEqual(list(fit_values), ["slim", "Tailored", "Regular", "Relaxed", "Oversized"])
		self.assertEqual(fit_values["slim"], "SL")

	def test_empty_category_gets_only_the_every_store_set(self):
		with patch("commera.store_options.CATEGORY_OPTIONS", {"Fashion": {"Zz Only Fashion": ["A"]}}):
			add_store_options("")
			add_store_options("Other")
		self.assertFalse(frappe.db.exists("Item Attribute", "Zz Only Fashion"))
		self.assertLessEqual(set(EVERY_STORE_OPTIONS["Size"]), set(get_values_by_attribute(["Size"])["Size"]))

	def test_short_sizes_take_the_abbreviations_of_unused_long_sizes(self):
		make_attribute(TEST_SIZE, [("Small", "S"), ("Large", "L")])

		with (
			patch("commera.store_options.EVERY_STORE_OPTIONS", {TEST_SIZE: ["S", "M", "L"]}),
			patch("commera.store_options.CATEGORY_OPTIONS", {}),
		):
			add_store_options("")

		self.assertEqual(
			get_values_by_attribute([TEST_SIZE])[TEST_SIZE],
			{"Small": "SMALL", "Large": "LARGE", "S": "S", "M": "M", "L": "L"},
		)

	def test_a_used_long_size_keeps_its_abbreviation(self):
		attribute = frappe.new_doc("Item Attribute")
		attribute.attribute_name = TEST_SIZE
		attribute.append("item_attribute_values", {"attribute_value": "Small", "abbr": "S"})

		append_attribute_values(attribute, ["S"], {"Small"})

		self.assertEqual(
			{row.attribute_value: row.abbr for row in attribute.item_attribute_values},
			{"Small": "S", "S": "S2"},
		)

	def test_picker_hides_unused_long_sizes_beside_their_short_size(self):
		make_attribute(TEST_SIZE, [("Small", "SMALL"), ("Large", "LARGE"), ("S", "S"), ("Huge", "H")])

		with patch("commera.api.admin.catalog.SUPERSEDED_VALUES", {TEST_SIZE: {"Small": "S", "Large": "L"}}):
			values = [row["value"] for row in get_attribute_values(TEST_SIZE)]
			listed = next(row for row in get_attributes() if row["name"] == TEST_SIZE)

		self.assertEqual(values, ["Large", "S", "Huge"])
		self.assertEqual([row["value"] for row in listed["values"]], ["Large", "S", "Huge"])

	def test_picker_keeps_a_long_size_a_product_uses(self):
		with patch("commera.api.admin.catalog.SUPERSEDED_VALUES", {TEST_SIZE: {"Small": "S"}}):
			values = get_picker_values(TEST_SIZE, ["Small", "S"], {(TEST_SIZE, "Small"): 1})

		self.assertEqual(values, ["Small", "S"])

	def test_title_attribute_is_not_offered_as_an_option(self):
		ensure_attribute_exists(DEFAULT_OPTION_ATTRIBUTE, DEFAULT_OPTION_VALUE, "STD")

		self.assertNotIn(DEFAULT_OPTION_ATTRIBUTE, [row["name"] for row in get_attributes()])
