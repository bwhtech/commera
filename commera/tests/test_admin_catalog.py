# Copyright (c) 2026, company@bwhstudios.com and Contributors
# Tests for the whole-product operations in api/admin/catalog.py: what delete_product refuses and
# what a refusal costs, and whether filing a product under a collection moves the storefront too.

import os

import frappe

from commera.api.admin.catalog import (
	add_products_to_collection,
	create_product,
	delete_product,
	get_product,
	get_product_chain,
	save_product_options,
	update_product,
)
from commera.tests.test_product_onboarding import ProductOnboardingTestCase


class DeleteProductTestCase(ProductOnboardingTestCase):
	def setUp(self):
		super().setUp()
		self.colour_attribute = self.make_named_attribute("Colour", ["Crimson", "Teal"])
		self.written_files = []

	def tearDown(self):
		# The DB rolls back with the test; the bytes under public/files do not.
		for path in self.written_files:
			if os.path.exists(path):
				os.remove(path)
		super().tearDown()

	def make_named_attribute(self, label, values):
		attribute = frappe.new_doc("Item Attribute")
		attribute.attribute_name = f"Deletion {label} {self.suffix}"
		for value in values:
			attribute.append("item_attribute_values", {"attribute_value": value, "abbr": value[:3].upper()})
		attribute.insert()
		return attribute.name

	def add_product(self):
		return create_product(
			title=f"Deletion Product {frappe.generate_hash(length=6).upper()}",
			collection=self.item_group,
			option_attribute=self.colour_attribute,
			size_attribute="Size",
			option_sizes=[{"option": "Crimson", "sizes": ["S", "M"]}],
		)["name"]

	def add_photo(self, variant_name):
		"""A real file on disk, attached the way the dashboard attaches one, so a delete that ran
		too early would take the bytes with it."""
		file_doc = frappe.new_doc("File")
		file_doc.file_name = f"deletion-{frappe.generate_hash(length=8)}.txt"
		# Identical content would be deduplicated onto one file_url and one set of bytes.
		file_doc.content = frappe.generate_hash(length=32)
		file_doc.is_private = 0
		file_doc.attached_to_doctype = "Style Attribute Variant"
		file_doc.attached_to_name = variant_name
		file_doc.insert()
		self.written_files.append(file_doc.get_full_path())

		frappe.get_doc("Style Attribute Variant", variant_name).add_images([file_doc.file_url])
		return file_doc

	def order_item(self, item_code):
		"""A Sales Order Item row against the size, which is what makes a product historical. Written
		as a child row on its own so the test needs no customer, company or fiscal year."""
		frappe.get_doc(
			{
				"doctype": "Sales Order Item",
				"parenttype": "Sales Order",
				"parentfield": "items",
				"parent": f"ZZ-DELETION-ORDER-{frappe.generate_hash(length=8)}",
				"item_code": item_code,
				"item_name": item_code,
				"qty": 1,
				"rate": 10,
				"uom": "Nos",
				"conversion_factor": 1,
				"delivery_date": frappe.utils.nowdate(),
			}
		).db_insert()


class TestDeleteProduct(DeleteProductTestCase):
	def test_a_never_touched_product_leaves_nothing_behind(self):
		item_template = self.add_product()
		chain = get_product_chain(item_template)
		self.assertTrue(chain["variants"])
		self.assertTrue(chain["item_codes"])

		delete_product(item_template)

		self.assertFalse(frappe.db.exists("Item", item_template))
		for item_code in chain["item_codes"]:
			self.assertFalse(frappe.db.exists("Item", item_code))
		for variant_name in chain["variants"]:
			self.assertFalse(frappe.db.exists("Style Attribute Variant", variant_name))
		for configurator in chain["configurators"]:
			self.assertFalse(frappe.db.exists("Style Attribute Configurator", configurator))
		self.assertFalse(
			frappe.db.exists(
				"Color Size Item",
				{"parent": ["in", chain["variants"]], "parenttype": "Style Attribute Variant"},
			)
		)

	def test_an_ordered_product_is_refused_with_its_photos_untouched(self):
		"""The refusal has to fire before anything is destroyed. delete_doc runs on_trash and the
		attachment sweep BEFORE it checks links, and a rolled-back delete does not put the bytes back."""
		item_template = self.add_product()
		chain = get_product_chain(item_template)
		photo = self.add_photo(chain["variants"][0])
		self.order_item(chain["item_codes"][0])

		with self.assertRaises(frappe.ValidationError) as refusal:
			delete_product(item_template)

		self.assertIn("ordered", str(refusal.exception))
		self.assertIn("Archive", str(refusal.exception))
		self.assertTrue(frappe.db.exists("Item", item_template))
		self.assertTrue(frappe.db.exists("File", photo.name))
		self.assertTrue(os.path.exists(photo.get_full_path()))

	def test_a_viewed_product_is_refused_in_words_rather_than_as_a_link_error(self):
		"""Storefront Analytics Event.item_code is a plain Link to Item that hooks.py does not ignore on
		delete, so a merely-viewed product is link-blocked - and raw LinkExistsError explains nothing."""
		item_template = self.add_product()
		chain = get_product_chain(item_template)
		photo = self.add_photo(chain["variants"][0])
		frappe.get_doc(
			{
				"doctype": "Storefront Analytics Event",
				"event": "view_item",
				"session_id": frappe.generate_hash(length=10),
				"item_code": chain["item_codes"][0],
			}
		).insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError) as refusal:
			delete_product(item_template)

		# Asserted first: this is the case that used to reach the delete loop, so it is the one that
		# proves the photos outlive a refusal - the ordered case was always caught before anything ran.
		self.assertTrue(os.path.exists(photo.get_full_path()))
		self.assertTrue(frappe.db.exists("File", photo.name))
		self.assertNotIsInstance(refusal.exception, frappe.LinkExistsError)
		self.assertIn("viewed", str(refusal.exception))
		self.assertIn("Archive", str(refusal.exception))
		self.assertTrue(frappe.db.exists("Item", item_template))


class TestProductCollection(DeleteProductTestCase):
	"""Style Attribute Variant carries its own item_group, and that copy - not Item.item_group - is what
	the storefront category pages and the search index read."""

	def setUp(self):
		super().setUp()
		self.item_template = self.add_product()
		self.other_collection = self.make_item_group()

	def make_item_group(self):
		item_group = frappe.new_doc("Item Group")
		item_group.item_group_name = f"Deletion Group {frappe.generate_hash(length=6).upper()}"
		item_group.parent_item_group = "All Item Groups"
		item_group.is_group = 0
		item_group.custom_displayname = item_group.item_group_name
		item_group.insert()
		return item_group.name

	def get_variant_collections(self):
		return frappe.get_all(
			"Style Attribute Variant",
			filters={"name": ["in", get_product_chain(self.item_template)["variants"]]},
			pluck="item_group",
		)

	def test_a_bulk_move_takes_the_options_with_it(self):
		add_products_to_collection([self.item_template], self.other_collection)

		self.assertEqual(frappe.db.get_value("Item", self.item_template, "item_group"), self.other_collection)
		self.assertEqual(set(self.get_variant_collections()), {self.other_collection})

	def test_the_product_screen_moves_the_options_the_same_way(self):
		update_product(self.item_template, collection=self.other_collection)

		self.assertEqual(set(self.get_variant_collections()), {self.other_collection})

	def test_both_writers_refuse_a_collection_that_holds_other_collections(self):
		"""One answer to "is this a valid collection?": update_product used to accept a structural
		parent that add_products_to_collection refused."""
		for move in (
			lambda: add_products_to_collection([self.item_template], "All Item Groups"),
			lambda: update_product(self.item_template, collection="All Item Groups"),
		):
			with self.assertRaises(frappe.ValidationError):
				move()


class TestSaveProductOptions(DeleteProductTestCase):
	def setUp(self):
		super().setUp()
		self.item_template = create_product(
			title=f"Options Product {frappe.generate_hash(length=6).upper()}",
			collection=self.item_group,
			option_attribute=self.colour_attribute,
			size_attribute="Size",
			option_sizes=[{"option": "Crimson", "sizes": ["S", "M"]}],
			price=500,
			sale_price=400,
		)["name"]

	def get_sizes(self):
		product = get_product(self.item_template)
		return {
			variant["option"]: {size["size"]: size for size in variant["sizes"]}
			for variant in product["variants"]
		}

	def test_a_new_size_joins_its_option_in_size_order_at_the_option_price(self):
		save_product_options(self.item_template, add=[{"option": "Crimson", "size": "XL"}])
		save_product_options(self.item_template, add=[{"option": "Crimson", "size": "L"}])

		crimson = self.get_sizes()["Crimson"]
		self.assertEqual(list(crimson), ["S", "M", "L", "XL"])
		self.assertEqual((crimson["L"]["default_rate"], crimson["L"]["sale_rate"]), (500, 400))

	def test_sizes_are_named_after_the_product_not_the_item_code(self):
		save_product_options(self.item_template, add=[{"option": "Teal", "size": "M"}])
		book = create_product(
			title=f"Book {frappe.generate_hash(length=6).upper()}", collection=self.item_group
		)

		names = frappe.get_all("Item", filters={"variant_of": self.item_template}, pluck="item_name")
		self.assertEqual(
			sorted(names),
			[f"{self.item_template} - {option}" for option in ("Crimson - M", "Crimson - S", "Teal - M")],
		)
		self.assertEqual(
			frappe.get_all("Item", filters={"variant_of": book["name"]}, pluck="item_name"), [book["name"]]
		)

	def test_a_new_option_gets_its_own_storefront_row(self):
		result = save_product_options(self.item_template, add=[{"option": "Teal", "size": "M"}])

		self.assertEqual(result["created"], 1)
		teal = self.get_sizes()["Teal"]
		self.assertEqual(list(teal), ["M"])
		self.assertEqual(teal["M"]["sale_rate"], 400)

	def test_a_removed_size_is_disabled_and_comes_back_as_the_same_item(self):
		medium = self.get_sizes()["Crimson"]["M"]["item_code"]

		result = save_product_options(self.item_template, remove=[{"option": "Crimson", "size": "M"}])

		self.assertEqual(result["disabled"], 1)
		self.assertEqual(list(self.get_sizes()["Crimson"]), ["S"])
		self.assertEqual(frappe.db.get_value("Item", medium, "disabled"), 1)

		result = save_product_options(self.item_template, add=[{"option": "Crimson", "size": "M"}])

		self.assertEqual((result["created"], result["restored"]), (0, 1))
		self.assertEqual(self.get_sizes()["Crimson"]["M"]["item_code"], medium)
		self.assertEqual(frappe.db.get_value("Item", medium, "disabled"), 0)

	def test_a_grid_opened_before_another_save_cannot_undo_it(self):
		save_product_options(self.item_template, add=[{"option": "Teal", "size": "S"}])

		save_product_options(self.item_template, add=[{"option": "Crimson", "size": "L"}])

		self.assertEqual(list(self.get_sizes()["Teal"]), ["S"])

	def test_an_option_with_every_size_removed_is_emptied_and_unpublished(self):
		save_product_options(self.item_template, add=[{"option": "Teal", "size": "S"}])
		teal_row = next(
			variant["name"]
			for variant in get_product(self.item_template)["variants"]
			if variant["option"] == "Teal"
		)
		self.add_photo(teal_row)
		frappe.db.set_value("Style Attribute Variant", teal_row, "is_published", 1)

		save_product_options(self.item_template, remove=[{"option": "Teal", "size": "S"}])

		self.assertEqual(self.get_sizes()["Teal"], {})
		self.assertEqual(frappe.db.get_value("Style Attribute Variant", teal_row, "is_published"), 0)

	def test_removing_every_variant_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			save_product_options(
				self.item_template,
				remove=[{"option": "Crimson", "size": "S"}, {"option": "Crimson", "size": "M"}],
			)
		self.assertEqual(set(self.get_sizes()["Crimson"]), {"S", "M"})
