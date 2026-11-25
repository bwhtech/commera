# Copyright (c) 2026, company@bwhstudios.com and Contributors
# Tests for the whole-product operations in api/admin/catalog.py: what delete_product refuses and
# what a refusal costs, and whether filing a product under a collection moves the storefront too.

import os
from unittest.mock import patch

import frappe
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

from commera.api.admin.catalog import (
	DEFAULT_OPTION_ATTRIBUTE,
	DEFAULT_OPTION_VALUE,
	DEFAULT_SIZE_VALUE,
	add_products_to_collection,
	create_product,
	delete_product,
	get_collection_product_counts,
	get_collections,
	get_product,
	get_product_chain,
	get_products,
	remove_products_from_collection,
	save_product_options,
	update_product,
)
from commera.patches import add_products_to_their_collection
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


class TestProductStatusFilter(DeleteProductTestCase):
	def setUp(self):
		super().setUp()
		self.published_product = self.add_product()
		self.unpublished_product = self.add_product()
		self.archived_product = self.add_product()
		for item_template, is_published in (
			(self.published_product, 1),
			(self.unpublished_product, 0),
			(self.archived_product, 0),
		):
			for variant_name in get_product_chain(item_template)["variants"]:
				frappe.db.set_value("Style Attribute Variant", variant_name, "is_published", is_published)
		frappe.db.set_value("Item", self.archived_product, "disabled", 1)

	def list_products(self, **filters):
		listed = get_products(collection=self.item_group, **filters)
		return {product["name"] for product in listed["products"]}, listed["total"]

	def test_a_product_with_no_published_option_is_unpublished(self):
		self.assertEqual(
			self.list_products(disabled=0, published=0), ({self.unpublished_product, self.item_template}, 2)
		)

	def test_a_product_with_a_published_option_is_published(self):
		self.assertEqual(self.list_products(disabled=0, published=1), ({self.published_product}, 1))

	def test_no_published_filter_lists_every_product(self):
		self.assertEqual(
			self.list_products(),
			(
				{self.published_product, self.unpublished_product, self.archived_product, self.item_template},
				4,
			),
		)
		self.assertEqual(self.list_products(disabled=1), ({self.archived_product}, 1))


class TestProductCollection(DeleteProductTestCase):
	"""A product sits in one or more collections. Style Attribute Variant carries its own copy of the
	primary one, and that copy - not Item.item_group - is what the storefront category pages read."""

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

	def get_collections(self):
		return get_product(self.item_template)["collections"]

	def test_adding_a_collection_keeps_the_others(self):
		add_products_to_collection([self.item_template], self.other_collection)

		self.assertEqual(self.get_collections(), [self.item_group, self.other_collection])
		self.assertEqual(frappe.db.get_value("Item", self.item_template, "item_group"), self.item_group)
		self.assertEqual(set(self.get_variant_collections()), {self.item_group})
		listed = get_products(collection=self.other_collection)["products"]
		self.assertEqual([product["name"] for product in listed], [self.item_template])
		self.assertEqual(listed[0]["collections"], [self.item_group, self.other_collection])
		self.assertEqual(get_collection_product_counts([self.other_collection]), {self.other_collection: 1})

	def test_removing_the_primary_promotes_the_next_collection(self):
		add_products_to_collection([self.item_template], self.other_collection)
		remove_products_from_collection([self.item_template], self.item_group)

		self.assertEqual(self.get_collections(), [self.other_collection])
		self.assertEqual(frappe.db.get_value("Item", self.item_template, "item_group"), self.other_collection)
		self.assertEqual(set(self.get_variant_collections()), {self.other_collection})
		listed = get_products(collection=self.item_group)["products"]
		self.assertNotIn(self.item_template, [product["name"] for product in listed])

	def test_a_product_keeps_its_last_collection(self):
		with self.assertRaises(frappe.ValidationError):
			remove_products_from_collection([self.item_template], self.item_group)
		self.assertEqual(self.get_collections(), [self.item_group])

	def test_the_product_screen_sets_the_primary_and_keeps_the_rest(self):
		update_product(self.item_template, collection=self.other_collection)

		self.assertEqual(self.get_collections(), [self.other_collection, self.item_group])
		self.assertEqual(set(self.get_variant_collections()), {self.other_collection})

	def test_the_product_screen_replaces_the_collections(self):
		update_product(self.item_template, collections=[self.other_collection, self.item_group])
		self.assertEqual(self.get_collections(), [self.other_collection, self.item_group])

		update_product(self.item_template, collections=[self.item_group])
		self.assertEqual(self.get_collections(), [self.item_group])
		self.assertEqual(set(self.get_variant_collections()), {self.item_group})

	def test_a_new_product_can_start_in_several_collections(self):
		item_template = create_product(
			title=f"Several {frappe.generate_hash(length=6).upper()}",
			collections=[self.other_collection, self.item_group],
		)["name"]

		self.assertEqual(get_product(item_template)["collections"], [self.other_collection, self.item_group])
		self.assertEqual(frappe.db.get_value("Item", item_template, "item_group"), self.other_collection)

	def test_every_writer_refuses_a_collection_that_holds_other_collections(self):
		for move in (
			lambda: add_products_to_collection([self.item_template], "All Item Groups"),
			lambda: update_product(self.item_template, collection="All Item Groups"),
			lambda: update_product(self.item_template, collections=[self.item_group, "All Item Groups"]),
		):
			with self.assertRaises(frappe.ValidationError):
				move()

	def test_the_picker_offers_only_collections_a_product_can_be_filed_under(self):
		self.assertEqual(get_collections(search_text=self.other_collection), [self.other_collection])
		self.assertNotIn("All Item Groups", get_collections(search_text="All Item Groups"))

	def test_a_desk_edit_of_the_item_group_makes_it_the_primary(self):
		item = frappe.get_doc("Item", self.item_template)
		item.append("custom_collections", {"item_group": self.item_group})
		item.item_group = self.other_collection
		item.save()

		self.assertEqual(self.get_collections(), [self.other_collection, self.item_group])

		# Reordering the rows alone moves item_group with them.
		item.reload()
		item.set("custom_collections", list(reversed(item.custom_collections)))
		item.save()
		self.assertEqual(frappe.db.get_value("Item", self.item_template, "item_group"), self.item_group)
		self.assertEqual(self.get_collections(), [self.item_group, self.other_collection])

	def test_a_discount_on_a_secondary_collection_applies_to_the_product(self):
		discount = frappe.new_doc("Commera Discount")
		discount.append(
			"targets", {"role": "Applies To", "target_type": "Item Group", "target": self.other_collection}
		)
		size = frappe._dict(
			item_code=get_product_chain(self.item_template)["item_codes"][0], item_group=self.item_group
		)
		self.assertFalse(discount.has_target_match(size, "Applies To"))

		add_products_to_collection([self.item_template], self.other_collection)
		self.assertTrue(discount.has_target_match(size, "Applies To"))

	@patch("commera.patches.add_products_to_their_collection.enqueue_full_rebuild")
	def test_the_patch_files_existing_products_under_their_item_group(self, enqueue_full_rebuild):
		frappe.db.delete("Product Collection", {"parenttype": "Item", "parent": self.item_template})

		add_products_to_their_collection.execute()
		add_products_to_their_collection.execute()

		self.assertEqual(self.get_collections(), [self.item_group])
		enqueue_full_rebuild.assert_called_once()


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

	def test_a_new_size_skips_a_compare_at_saved_below_the_price(self):
		frappe.db.set_value(
			"Item Price",
			{"price_list": self.default_price_list, "item_code": ["in", self.get_item_codes()]},
			"price_list_rate",
			300,
		)

		save_product_options(self.item_template, add=[{"option": "Crimson", "size": "L"}])

		large = self.get_sizes()["Crimson"]["L"]
		self.assertEqual((large["default_rate"], large["sale_rate"]), (None, 400))

	def get_item_codes(self):
		return [size["item_code"] for sizes in self.get_sizes().values() for size in sizes.values()]

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


class TestFirstOption(DeleteProductTestCase):
	def setUp(self):
		super().setUp()
		self.book = create_product(
			title=f"First Option Book {frappe.generate_hash(length=6).upper()}",
			collection=self.item_group,
			price=500,
			sale_price=400,
		)["name"]
		self.single_item = frappe.get_all("Item", filters={"variant_of": self.book}, pluck="name")[0]

	def placeholder(self):
		return [{"option": DEFAULT_OPTION_VALUE, "size": DEFAULT_SIZE_VALUE}]

	def get_sizes(self):
		return {
			variant["option"]: {size["size"]: size for size in variant["sizes"]}
			for variant in get_product(self.book)["variants"]
		}

	def listed_item_codes(self):
		return {size["item_code"] for sizes in self.get_sizes().values() for size in sizes.values()}

	def enabled_item_codes(self):
		return set(frappe.get_all("Item", filters={"variant_of": self.book, "disabled": 0}, pluck="name"))

	def add_colours(self):
		return save_product_options(
			self.book,
			add=[{"option": "Crimson", "size": "S"}, {"option": "Teal", "size": "S"}],
			remove=self.placeholder(),
			option_attribute=self.colour_attribute,
		)

	def test_a_product_without_history_takes_its_first_colour_at_its_price(self):
		result = self.add_colours()

		product = get_product(self.book)
		self.assertEqual(product["option_attribute"], self.colour_attribute)
		self.assertEqual((result["created"], result["disabled"]), (2, 1))
		sizes = self.get_sizes()
		self.assertEqual(set(sizes), {"Crimson", "Teal"})
		for option in ("Crimson", "Teal"):
			self.assertEqual(
				(sizes[option]["S"]["default_rate"], sizes[option]["S"]["sale_rate"]), (500, 400)
			)
		self.assertEqual(frappe.db.get_value("Item", self.single_item, "disabled"), 1)
		self.assertEqual(self.enabled_item_codes(), self.listed_item_codes())

	def test_stock_and_orders_stay_on_the_single_item_that_goes_off_sale(self):
		make_stock_entry(item_code=self.single_item, qty=5, to_warehouse=self.warehouse, rate=100)
		self.order_item(self.single_item)

		self.add_colours()

		self.assertEqual(frappe.db.get_value("Item", self.single_item, "disabled"), 1)
		self.assertEqual(
			frappe.db.get_value(
				"Bin", {"item_code": self.single_item, "warehouse": self.warehouse}, "actual_qty"
			),
			5,
		)
		self.assertTrue(frappe.db.exists("Sales Order Item", {"item_code": self.single_item}))
		self.assertEqual({size["stock"] for size in self.get_sizes()["Crimson"].values()}, {0})
		self.assertEqual(self.get_sizes()["Teal"]["S"]["sale_rate"], 400)
		self.assertEqual(self.enabled_item_codes(), self.listed_item_codes())

	def test_sizes_alone_keep_the_hidden_option(self):
		save_product_options(
			self.book,
			add=[
				{"option": DEFAULT_OPTION_VALUE, "size": "S"},
				{"option": DEFAULT_OPTION_VALUE, "size": "M"},
			],
			remove=self.placeholder(),
		)

		self.assertEqual(get_product(self.book)["option_attribute"], DEFAULT_OPTION_ATTRIBUTE)
		standard = self.get_sizes()[DEFAULT_OPTION_VALUE]
		self.assertEqual(list(standard), ["S", "M"])
		self.assertEqual((standard["M"]["default_rate"], standard["M"]["sale_rate"]), (500, 400))
		self.assertEqual(frappe.db.get_value("Item", self.single_item, "disabled"), 1)
		self.assertEqual(self.enabled_item_codes(), self.listed_item_codes())

	def test_a_product_that_already_varies_cannot_switch_its_option(self):
		self.add_colours()
		other_attribute = self.make_named_attribute("Pattern", ["Plain"])

		with self.assertRaises(frappe.ValidationError):
			save_product_options(
				self.book, add=[{"option": "Plain", "size": "S"}], option_attribute=other_attribute
			)
		self.assertEqual(get_product(self.book)["option_attribute"], self.colour_attribute)

	def test_size_is_not_an_option_axis(self):
		with self.assertRaises(frappe.ValidationError):
			save_product_options(self.book, add=[{"option": "S", "size": "S"}], option_attribute="Size")
		self.assertEqual(get_product(self.book)["option_attribute"], DEFAULT_OPTION_ATTRIBUTE)
