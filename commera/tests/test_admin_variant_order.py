# Copyright (c) 2026, company@bwhstudios.com and Contributors

import frappe

from commera.api.admin.catalog import (
	create_product,
	get_product,
	move_product_image,
	remove_product_image,
	sort_by_size_order,
)
from commera.tests.test_admin_catalog import DeleteProductTestCase


class TestVariantOrder(DeleteProductTestCase):
	"""get_product returns colours and sizes in one stable order, whatever order the items were made in."""

	def setUp(self):
		super().setUp()
		self.item_template = create_product(
			title=f"Order Product {frappe.generate_hash(length=6).upper()}",
			collection=self.item_group,
			option_attribute=self.colour_attribute,
			size_attribute="Size",
			option_sizes=[
				{"option": "Crimson", "sizes": ["L", "S", "M"]},
				{"option": "Teal", "sizes": ["M", "S"]},
			],
			price=500,
		)["name"]

	def size_ranks(self):
		values = frappe.get_all(
			"Item Attribute Value", filters={"parent": "Size"}, order_by="idx asc", pluck="attribute_value"
		)
		return {value: rank for rank, value in enumerate(values)}

	def test_sizes_follow_the_size_attribute_order(self):
		ranks = self.size_ranks()
		for variant in get_product(self.item_template)["variants"]:
			sizes = [size["size"] for size in variant["sizes"]]
			self.assertEqual(sizes, sorted(sizes, key=ranks.get), variant["option"])

	def test_colours_keep_the_order_they_were_typed_in(self):
		"""generate_variants makes the colour rows in no particular order; the seller typed Crimson first."""
		options = [variant["option"] for variant in get_product(self.item_template)["variants"]]
		self.assertEqual(options, ["Crimson", "Teal"])

	def test_an_unlisted_size_goes_after_the_listed_ones(self):
		first, second = list(self.size_ranks())[:2]
		rows = [{"size": "Not A Size"}, {"size": second}, {"size": first}]
		self.assertEqual(
			[row["size"] for row in sort_by_size_order(rows, lambda row: row["size"])],
			[first, second, "Not A Size"],
		)

	def test_a_photo_moves_to_the_cover_and_a_removed_one_comes_back_in_place(self):
		variant = get_product(self.item_template)["variants"][0]["name"]
		first, second, third = (self.add_photo(variant).file_url for _ in range(3))

		move_product_image(variant, third, 0)
		self.assertEqual(get_product(self.item_template)["variants"][0]["images"], [third, first, second])

		remove_product_image(variant, first)
		frappe.get_doc("Style Attribute Variant", variant).add_images([first])
		move_product_image(variant, first, 1)
		self.assertEqual(get_product(self.item_template)["variants"][0]["images"], [third, first, second])
