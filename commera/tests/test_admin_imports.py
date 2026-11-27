# Copyright (c) 2026, company@bwhstudios.com and Contributors
# Tests for imports: the mapping, the row rules shared with the Add product dialog, run_import's photo
# half, and Publish all.

import os
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin.import_rows import suggest_mapping
from commera.api.admin.imports import (
	OPTION_ATTRIBUTE,
	get_image_group_key,
	parse_and_validate,
	publish_imported_products,
	run_import,
)

SIZE_ATTRIBUTE = "Size"

TITLE_PREFIX = "ZZ Import"


class RunImportTestCase(IntegrationTestCase):
	def setUp(self):
		for attribute in (OPTION_ATTRIBUTE, SIZE_ATTRIBUTE):
			if not frappe.db.exists("Item Attribute", attribute):
				self.skipTest(f'this site has no Item Attribute named "{attribute}"')

		self.suffix = frappe.generate_hash(length=6).upper()
		self.title = f"{TITLE_PREFIX} {self.suffix}"
		self.color = f"Zinc{self.suffix}"
		self.collection = self.make_item_group()
		self.written_files = []

	def tearDown(self):
		# The DB rolls back with the test; the bytes under public/files do not.
		for path in self.written_files:
			if os.path.exists(path):
				os.remove(path)

	def make_item_group(self):
		item_group = frappe.new_doc("Item Group")
		item_group.item_group_name = f"Import Group {self.suffix}"
		item_group.parent_item_group = "All Item Groups"
		item_group.is_group = 0
		# commera makes the storefront display name mandatory on Item Group.
		item_group.custom_displayname = item_group.item_group_name
		item_group.insert()
		return item_group.name

	def make_import_file(self, rows=None):
		rows = rows or [
			"Product Title,Collection,Color,Size,Compare at price,Selling price,Stock",
			f"{self.title},{self.collection},{self.color},S,120,99,0",
			f"{self.title},{self.collection},{self.color},M,120,99,0",
		]
		file_doc = frappe.new_doc("File")
		file_doc.file_name = f"import-{self.suffix}.csv"
		file_doc.content = "\n".join(rows)
		file_doc.is_private = 0
		file_doc.insert()
		self.written_files.append(file_doc.get_full_path())
		return file_doc.file_url

	def make_photo(self):
		file_doc = frappe.new_doc("File")
		file_doc.file_name = f"photo-{frappe.generate_hash(length=8)}.txt"
		# Identical content would be deduplicated onto one file_url.
		file_doc.content = frappe.generate_hash(length=32)
		file_doc.is_private = 0
		file_doc.insert()
		self.written_files.append(file_doc.get_full_path())
		return file_doc.file_url

	def get_created_titles(self):
		return frappe.get_all("Item", filters={"item_name": self.title}, pluck="name")


class TestRunImportImages(RunImportTestCase):
	def test_a_group_whose_photos_will_not_attach_still_leaves_its_product(self):
		"""The photos sit inside their own savepoint, so a variant that refuses them costs the
		merchant a message about the photos and not the product it just spent a minute describing."""
		file_url = self.make_import_file()
		assignments = {get_image_group_key(self.title, self.color): [self.make_photo()]}

		with patch(
			"commera.commera_ecommerce.doctype.style_attribute_variant.style_attribute_variant"
			".StyleAttributeVariant.add_images",
			side_effect=frappe.ValidationError("this variant will not take photos"),
		):
			result = run_import(file_url, image_assignments=assignments)

		self.assertEqual(result["created_count"], 1)
		self.assertEqual(result["images_attached"], 0)
		self.assertTrue(result["image_errors"])
		self.assertIn("will not take photos", result["image_errors"][0]["message"])
		self.assertEqual(self.get_created_titles(), [result["created"][0]["item_template"]])

	def test_photos_land_on_the_colour_they_were_assigned_to(self):
		file_url = self.make_import_file()
		photo_url = self.make_photo()

		result = run_import(
			file_url, image_assignments={get_image_group_key(self.title, self.color): [photo_url]}
		)

		self.assertEqual(result["images_attached"], 1)
		self.assertEqual(result["image_errors"], [])
		variant = frappe.get_doc(
			"Style Attribute Variant",
			frappe.db.get_value(
				"Style Attribute Variant", {"item_style": result["created"][0]["item_template"]}
			),
		)
		self.assertEqual([row.image for row in variant.images], [photo_url])

	def test_one_colour_spelled_two_ways_does_not_attach_its_photos_twice(self):
		"""The group key casefolds the colour, so a file mixing "Zinc" and "zinc" describes one
		variant - keying the attach map on the raw spelling handed it the same photos twice."""
		photo_url = self.make_photo()
		file_doc = frappe.new_doc("File")
		file_doc.file_name = f"import-mixed-{self.suffix}.csv"
		file_doc.content = "\n".join(
			[
				"Product Title,Collection,Color,Size,Compare at price,Selling price,Stock",
				f"{self.title},{self.collection},{self.color},S,120,99,0",
				f"{self.title},{self.collection},{self.color.lower()},M,120,99,0",
			]
		)
		file_doc.is_private = 0
		file_doc.insert()
		self.written_files.append(file_doc.get_full_path())

		result = run_import(
			file_doc.file_url,
			image_assignments={get_image_group_key(self.title, self.color): [photo_url]},
		)

		self.assertEqual(result["images_attached"], 1)


class TestRunImportImageAssignmentShape(RunImportTestCase):
	"""A payload of the wrong shape used to reach .items() after the creation loop, outside every
	savepoint: the AttributeError rolled the request back and took the created products with it."""

	def test_a_list_is_refused_as_a_validation_error(self):
		"""Sent as JSON, the way a form-encoded request carries it - frappe's own type check on the
		endpoint only sees a string, and parse_json hands back the list."""
		file_url = self.make_import_file()

		with self.assertRaises(frappe.ValidationError):
			run_import(file_url, image_assignments=frappe.as_json(["/files/loose.png"]))

		self.assertEqual(self.get_created_titles(), [])

	def test_a_string_is_refused_as_a_validation_error(self):
		file_url = self.make_import_file()

		with self.assertRaises(frappe.ValidationError):
			run_import(file_url, image_assignments='"just a string"')

		self.assertEqual(self.get_created_titles(), [])

	def test_a_group_whose_photos_are_not_a_list_is_refused(self):
		file_url = self.make_import_file()

		with self.assertRaises(frappe.ValidationError):
			run_import(file_url, image_assignments={"a-group": "/files/one.png"})

		self.assertEqual(self.get_created_titles(), [])

	def test_a_private_photo_is_refused_rather_than_pinned_to_a_public_page(self):
		"""add_images only asks whether some File row carries the url, so anyone holding Item-create
		could publish a private attachment they do not own."""
		file_url = self.make_import_file()
		private_file = frappe.new_doc("File")
		private_file.file_name = f"private-{frappe.generate_hash(length=8)}.txt"
		private_file.content = frappe.generate_hash(length=32)
		private_file.is_private = 1
		private_file.insert()
		self.written_files.append(private_file.get_full_path())

		with self.assertRaises(frappe.ValidationError) as refusal:
			run_import(
				file_url,
				image_assignments={get_image_group_key(self.title, self.color): [private_file.file_url]},
			)

		self.assertIn("private", str(refusal.exception))
		self.assertEqual(self.get_created_titles(), [])


class TestImportPrices(RunImportTestCase):
	def test_a_row_without_a_price_is_refused(self):
		file_url = self.make_import_file(
			[
				"Product Title,Collection,Color,Size,Price,Discounted price,Stock",
				f"{self.title},{self.collection},{self.color},S,120,,0",
			]
		)

		issue = parse_and_validate(file_url)["rows"][0]["issue"]

		self.assertEqual(issue, {"level": "error", "text": "Price is missing"})

	def test_a_single_price_column_is_what_the_shopper_pays(self):
		file_url = self.make_import_file(
			[
				"Product Title,Collection,Color,Size,MRP,Stock",
				f"{self.title},{self.collection},{self.color},S,120,0",
			]
		)

		result = parse_and_validate(file_url)

		self.assertEqual(result["mapping"]["MRP"], "sale_price")
		row = result["rows"][0]
		self.assertEqual((row["sale_price"], row["compare_at_price"], row["issue"]), (120, 0, None))

	def test_an_original_price_below_the_price_is_refused_in_the_add_dialog_words(self):
		file_url = self.make_import_file(
			[
				"Product Title,Collection,Color,Size,Price,Discounted price,Stock",
				f"{self.title},{self.collection},{self.color},S,1000,1200,0",
			]
		)

		issue = parse_and_validate(file_url)["rows"][0]["issue"]

		self.assertEqual(issue, {"level": "error", "text": "Original price must be higher than the price."})

	def test_a_plain_price_next_to_a_discounted_price_is_the_original_price(self):
		mapping, _confidence = suggest_mapping(["Price", "Discounted price"])

		self.assertEqual(mapping, {"Price": "compare_at_price", "Discounted price": "sale_price"})


class TestImportMapping(RunImportTestCase):
	def test_an_unknown_header_is_a_low_confidence_guess_not_a_refusal(self):
		mapping, confidence = suggest_mapping(
			["Title", "Variant Size", "Variant Compare At Price", "Variant Price"]
		)

		self.assertEqual(
			mapping,
			{
				"Title": "title",
				"Variant Size": "size",
				"Variant Compare At Price": "compare_at_price",
				"Variant Price": "sale_price",
			},
		)
		self.assertEqual(confidence["Variant Size"], "low")

	def test_a_file_missing_a_required_column_still_reads(self):
		"""The Map step is where a missing column is fixed, so reading the file must not refuse it."""
		file_url = self.make_import_file(["Name,Supplier code", f"{self.title},SUP-1"])

		result = parse_and_validate(file_url)

		self.assertEqual(result["missing"], ["sale_price", "collection"])
		self.assertEqual(result["rows"], [])
		self.assertEqual(result["counts"]["total"], 1)
		self.assertEqual(result["preview"], [[self.title, "SUP-1"]])
		self.assertEqual(result["samples"]["Supplier code"], "SUP-1")

	def test_run_import_refuses_a_mapping_with_a_required_field_missing(self):
		file_url = self.make_import_file(["Name,Price", f"{self.title},99"])

		with self.assertRaises(frappe.ValidationError):
			run_import(file_url)

	def test_one_collection_for_every_row_fills_a_missing_collection_column(self):
		file_url = self.make_import_file(["Name,Price", f"{self.title},99"])

		result = parse_and_validate(file_url, default_collection=self.collection)

		self.assertEqual(result["missing"], [])
		self.assertEqual(result["rows"][0]["collection"], self.collection)
		self.assertIsNone(result["rows"][0]["issue"])


class TestImportOptions(RunImportTestCase):
	def get_sizes(self, item_template):
		variants = frappe.get_all(
			"Style Attribute Variant", filters={"item_style": item_template}, pluck="name"
		)
		return sorted(
			frappe.get_all(
				"Color Size Item",
				filters={"parent": ["in", variants], "parenttype": "Style Attribute Variant"},
				pluck="size",
			)
		)

	def test_counts_say_products_and_variants_not_rows(self):
		result = parse_and_validate(self.make_import_file())

		self.assertEqual((result["counts"]["products"], result["counts"]["variants"]), (1, 2))

	def test_a_product_with_no_color_or_size_imports_with_no_variants(self):
		file_url = self.make_import_file(
			["Product Title,Collection,Price,Stock", f"{self.title},{self.collection},450,3"]
		)

		counts = parse_and_validate(file_url)["counts"]
		result = run_import(file_url)

		self.assertEqual((counts["products"], counts["variants"]), (1, 0))
		self.assertEqual(result["row_errors"], [])
		self.assertEqual(len(self.get_sizes(result["created"][0]["item_template"])), 1)

	def test_sizes_without_a_color_become_one_variant_each(self):
		file_url = self.make_import_file(
			[
				"Product Title,Collection,Size,Price",
				f"{self.title},{self.collection},S,99",
				f"{self.title},{self.collection},M,99",
			]
		)

		result = run_import(file_url)

		self.assertEqual(result["row_errors"], [])
		self.assertEqual(self.get_sizes(result["created"][0]["item_template"]), ["M", "S"])

	def test_a_product_mixing_rows_with_and_without_a_color_is_an_error(self):
		file_url = self.make_import_file(
			[
				"Product Title,Collection,Color,Size,Price",
				f"{self.title},{self.collection},{self.color},S,99",
				f"{self.title},{self.collection},,M,99",
			]
		)

		issue = parse_and_validate(file_url)["rows"][1]["issue"]

		self.assertEqual(issue["level"], "error")
		self.assertIn("color", issue["text"])

	def test_photos_land_on_a_product_with_no_color(self):
		file_url = self.make_import_file(
			["Product Title,Collection,Price", f"{self.title},{self.collection},450"]
		)

		result = run_import(
			file_url, image_assignments={get_image_group_key(self.title, ""): [self.make_photo()]}
		)

		self.assertEqual((result["images_attached"], result["image_errors"]), (1, []))


class TestPublishImportedProducts(RunImportTestCase):
	def test_publish_all_puts_every_imported_draft_live(self):
		result = run_import(self.make_import_file())
		item_template = result["created"][0]["item_template"]

		published = publish_imported_products([item_template])

		self.assertEqual(published, {"published": 1, "not_published": []})
		self.assertEqual(
			frappe.get_all(
				"Style Attribute Variant", filters={"item_style": item_template}, pluck="is_published"
			),
			[1],
		)
