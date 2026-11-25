# Copyright (c) 2026, company@bwhstudios.com and Contributors
# Tests for imports.run_import's photo half: a product survives its own photos failing, and a
# malformed image_assignments payload is refused instead of taking the import down with it.

import os
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera.api.admin.imports import (
	OPTION_ATTRIBUTE,
	SIZE_ATTRIBUTE,
	get_image_group_key,
	parse_and_validate,
	run_import,
)

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
	def test_a_row_without_a_discounted_price_is_refused(self):
		file_url = self.make_import_file(
			[
				"Product Title,Collection,Color,Size,Price,Discounted price,Stock",
				f"{self.title},{self.collection},{self.color},S,120,,0",
			]
		)

		issue = parse_and_validate(file_url)["rows"][0]["issue"]

		self.assertEqual(issue, {"level": "error", "text": "Discounted price is missing"})

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

	def test_a_price_below_the_discounted_price_is_refused(self):
		file_url = self.make_import_file(
			[
				"Product Title,Collection,Color,Size,Price,Discounted price,Stock",
				f"{self.title},{self.collection},{self.color},S,1000,1200,0",
			]
		)

		issue = parse_and_validate(file_url)["rows"][0]["issue"]

		self.assertEqual(issue, {"level": "error", "text": "Price must be higher than the discounted price"})
