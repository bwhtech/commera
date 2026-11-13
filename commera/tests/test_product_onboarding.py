# Copyright (c) 2026, company@bwhstudios.com and Contributors
# Tests for the Ecommerce-tab backend: the Style Attribute Variant image/price/stock methods,
# the bulk variant pricing API and the batched stock reader. Real-DB, auto-rolled-back.

import frappe
from erpnext.controllers.item_variant import create_variant
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from commera.api.admin.catalog import (
	DEFAULT_OPTION_ATTRIBUTE,
	DEFAULT_OPTION_VALUE,
	DEFAULT_SIZE_VALUE,
	SIZE_ATTRIBUTE,
	create_product,
	get_attribute_values,
	get_product,
	get_size_prices,
	update_product,
)
from commera.api.admin.inventory import LOW_STOCK_THRESHOLD, get_inventory
from commera.api.admin.orders import get_overview
from commera.api.utils import get_stock_for_items
from commera.api.variant_pricing import set_variant_prices

# "L" is deliberately unused by the variant under test, leaving a second leaf SKU available.
ATTRIBUTE_VALUES = ["S", "M", "L"]
SIZES = ["S", "M"]


class ProductOnboardingTestCase(IntegrationTestCase):
	def setUp(self):
		self.suffix = frappe.generate_hash(length=6).upper()
		self.default_price_list = self.make_price_list("Default")
		self.sale_price_list = self.make_price_list("Sale")
		self.warehouse = frappe.db.get_value("Warehouse", {"is_group": 0}, "name")
		settings = frappe.get_doc("Commera Settings")
		settings.default_price_list = self.default_price_list
		settings.sale_price_list = self.sale_price_list
		settings.ecommerce_warehouse = self.warehouse
		settings.save()
		frappe.clear_document_cache("Commera Settings", "Commera Settings")

		self.attribute = self.make_item_attribute()
		self.item_group = self.make_item_group()
		self.item_template = self.make_item_template()
		self.size_item_codes = [self.make_size_item(size) for size in SIZES]
		self.variant = self.make_style_attribute_variant(dict(zip(SIZES, self.size_item_codes, strict=True)))

	def make_price_list(self, label):
		price_list = frappe.new_doc("Price List")
		price_list.price_list_name = f"Onboarding {label} {self.suffix}"
		price_list.currency = frappe.defaults.get_global_default("currency") or "INR"
		price_list.selling = 1
		price_list.enabled = 1
		price_list.insert()
		return price_list.name

	def make_item_group(self):
		item_group = frappe.new_doc("Item Group")
		item_group.item_group_name = f"Onboarding Group {self.suffix}"
		item_group.parent_item_group = "All Item Groups"
		item_group.is_group = 0
		# commera makes the storefront display name mandatory on Item Group.
		item_group.custom_displayname = item_group.item_group_name
		item_group.insert()
		return item_group.name

	def make_item_attribute(self):
		attribute = frappe.new_doc("Item Attribute")
		attribute.attribute_name = f"Onboarding Size {self.suffix}"
		for attribute_value in ATTRIBUTE_VALUES:
			attribute.append(
				"item_attribute_values", {"attribute_value": attribute_value, "abbr": attribute_value}
			)
		attribute.insert()
		return attribute.name

	def make_item_template(self):
		item = frappe.new_doc("Item")
		item.item_code = f"ONB-TEMPLATE-{frappe.generate_hash(length=8).upper()}"
		item.item_name = item.item_code
		item.item_group = self.item_group
		item.stock_uom = "Nos"
		item.is_stock_item = 1
		item.has_variants = 1
		item.variant_based_on = "Item Attribute"
		item.append("attributes", {"attribute": self.attribute})
		item.insert()
		return item.name

	def make_size_item(self, size, item_template=None):
		size_item = create_variant(item_template or self.item_template, {self.attribute: size})
		size_item.insert()
		return size_item.name

	def make_plain_item(self):
		item = frappe.new_doc("Item")
		item.item_code = f"ONB-PLAIN-{frappe.generate_hash(length=8).upper()}"
		item.item_name = item.item_code
		item.item_group = self.item_group
		item.stock_uom = "Nos"
		item.is_stock_item = 1
		item.insert()
		return item.name

	def make_style_attribute_variant(self, sizes_by_item_code, item_template=None):
		item_template = item_template or self.item_template
		configurator = frappe.new_doc("Style Attribute Configurator")
		configurator.item_template = item_template
		configurator.item_attribute = self.attribute
		configurator.insert(ignore_if_duplicate=True)

		attribute_value = frappe.generate_hash(length=6).upper()
		variant = frappe.new_doc("Style Attribute Variant")
		variant.configurator = configurator.name
		variant.item_style = item_template
		variant.attribute_value = attribute_value
		variant.display_name = f"Colour {attribute_value}"
		for size, item_code in sizes_by_item_code.items():
			variant.append("sizes", {"size": size, "item_code": item_code})
		variant.insert()
		return variant

	def make_file(self):
		file_doc = frappe.new_doc("File")
		# Identical content would be deduplicated onto one file_url, collapsing two "different" images.
		file_doc.file_name = f"{frappe.generate_hash(length=8)}.txt"
		file_doc.content = frappe.generate_hash(length=16)
		file_doc.is_private = 0
		file_doc.insert()
		return file_doc.file_url

	def get_price(self, item_code, price_list):
		return frappe.db.get_value(
			"Item Price", {"item_code": item_code, "price_list": price_list}, "price_list_rate"
		)


class TestVariantImages(ProductOnboardingTestCase):
	def test_add_images_appends_one_row_per_url(self):
		file_urls = [self.make_file(), self.make_file()]
		self.variant.add_images(file_urls)

		self.variant.reload()
		self.assertEqual([row.image for row in self.variant.images], file_urls)

	def test_add_images_accepts_a_json_string(self):
		file_url = self.make_file()
		self.variant.add_images(frappe.as_json([file_url]))

		self.variant.reload()
		self.assertEqual([row.image for row in self.variant.images], [file_url])

	def test_add_images_rejects_a_url_with_no_file_record(self):
		with self.assertRaises(frappe.ValidationError):
			self.variant.add_images(["/files/never-uploaded.png"])

		self.variant.reload()
		self.assertEqual(self.variant.images, [])

	def test_remove_image_drops_only_the_matching_row(self):
		kept_url, removed_url = self.make_file(), self.make_file()
		self.variant.add_images([kept_url, removed_url])

		self.variant.remove_image(removed_url)

		self.variant.reload()
		self.assertEqual([row.image for row in self.variant.images], [kept_url])

	def test_remove_image_rejects_a_url_not_on_the_variant(self):
		self.variant.add_images([self.make_file()])

		with self.assertRaises(frappe.ValidationError):
			self.variant.remove_image("/files/not-on-this-variant.png")

		self.variant.reload()
		self.assertEqual(len(self.variant.images), 1)

	def test_clear_images_empties_the_table(self):
		self.variant.add_images([self.make_file(), self.make_file()])

		self.variant.clear_images()

		self.variant.reload()
		self.assertEqual(self.variant.images, [])

	def test_clearing_images_unpublishes_the_variant(self):
		# The publish gate is the reason the Ecommerce tab shows a blocked reason at all.
		self.variant.add_images([self.make_file()])
		self.variant.reload()
		self.variant.is_published = 1
		self.variant.save()
		self.assertEqual(self.variant.is_published, 1)

		self.variant.clear_images()

		self.assertEqual(frappe.db.get_value("Style Attribute Variant", self.variant.name, "is_published"), 0)


class TestSizePrices(ProductOnboardingTestCase):
	def test_save_size_prices_creates_a_row_per_size_and_price_list(self):
		small, medium = self.size_item_codes

		counts = self.variant.save_size_prices(
			[
				{"item_code": small, "default_rate": 100, "sale_rate": 80},
				{"item_code": medium, "default_rate": 120, "sale_rate": 90},
			]
		)

		self.assertEqual(counts, {"created": 4, "updated": 0})
		self.assertEqual(self.get_price(small, self.default_price_list), 100)
		self.assertEqual(self.get_price(small, self.sale_price_list), 80)
		self.assertEqual(self.get_price(medium, self.default_price_list), 120)
		self.assertEqual(self.get_price(medium, self.sale_price_list), 90)

	def test_save_size_prices_updates_the_existing_row_instead_of_adding_one(self):
		small = self.size_item_codes[0]
		self.variant.save_size_prices([{"item_code": small, "default_rate": 100}])

		counts = self.variant.save_size_prices([{"item_code": small, "default_rate": 150}])

		self.assertEqual(counts, {"created": 0, "updated": 1})
		self.assertEqual(
			frappe.db.count("Item Price", {"item_code": small, "price_list": self.default_price_list}), 1
		)
		self.assertEqual(self.get_price(small, self.default_price_list), 150)

	def test_save_size_prices_leaves_a_blank_rate_alone(self):
		# A blank cell in the price grid means "not my business", never "delete this price".
		small = self.size_item_codes[0]
		self.variant.save_size_prices([{"item_code": small, "default_rate": 100, "sale_rate": 80}])

		counts = self.variant.save_size_prices([{"item_code": small, "default_rate": 100}])

		self.assertEqual(counts, {"created": 0, "updated": 0})
		self.assertEqual(self.get_price(small, self.sale_price_list), 80)

	def test_save_size_prices_rejects_an_item_that_is_not_a_size_of_this_variant(self):
		foreign_item_code = self.make_plain_item()

		with self.assertRaises(frappe.ValidationError):
			self.variant.save_size_prices([{"item_code": foreign_item_code, "default_rate": 100}])

		self.assertFalse(self.get_price(foreign_item_code, self.default_price_list))

	def test_get_size_prices_reads_back_what_save_size_prices_wrote(self):
		small, medium = self.size_item_codes
		self.variant.save_size_prices(
			[
				{"item_code": small, "default_rate": 100, "sale_rate": 80},
				{"item_code": medium, "default_rate": 120},
			]
		)

		size_prices = self.variant.get_size_prices()

		self.assertEqual(size_prices["default_price_list"], self.default_price_list)
		self.assertEqual(size_prices["sale_price_list"], self.sale_price_list)
		self.assertEqual(
			size_prices["sizes"],
			[
				{"size": "S", "item_code": small, "default_rate": 100, "sale_rate": 80},
				{"size": "M", "item_code": medium, "default_rate": 120, "sale_rate": None},
			],
		)


class TestSetVariantPrices(ProductOnboardingTestCase):
	def test_prices_every_leaf_sku_under_the_template(self):
		counts = set_variant_prices(self.item_template, default_rate=200, sale_rate=150)

		self.assertEqual(counts, {"created": 4, "updated": 0, "skipped": 0, "queued": 0})
		for item_code in self.size_item_codes:
			self.assertEqual(self.get_price(item_code, self.default_price_list), 200)
			self.assertEqual(self.get_price(item_code, self.sale_price_list), 150)

	def test_existing_prices_are_skipped_unless_overwrite_is_asked_for(self):
		set_variant_prices(self.item_template, default_rate=200)

		counts = set_variant_prices(self.item_template, default_rate=300)

		self.assertEqual(counts, {"created": 0, "updated": 0, "skipped": 2, "queued": 0})
		self.assertEqual(self.get_price(self.size_item_codes[0], self.default_price_list), 200)

	def test_an_expired_price_is_not_an_existing_price(self):
		set_variant_prices(self.item_template, default_rate=200)
		expired = {"valid_from": add_days(today(), -30), "valid_upto": add_days(today(), -1)}
		for item_code in self.size_item_codes:
			name = frappe.db.get_value("Item Price", {"item_code": item_code})
			frappe.get_doc("Item Price", name).update(expired).save()

		counts = set_variant_prices(self.item_template, default_rate=300)

		self.assertEqual(counts, {"created": 2, "updated": 0, "skipped": 0, "queued": 0})
		item_code = self.size_item_codes[0]
		self.assertEqual(get_size_prices([item_code])[item_code]["default_rate"], 300)

	def test_overwrite_existing_rewrites_the_stale_rows(self):
		set_variant_prices(self.item_template, default_rate=200)

		counts = set_variant_prices(self.item_template, default_rate=300, overwrite_existing=1)

		self.assertEqual(counts, {"created": 0, "updated": 2, "skipped": 0, "queued": 0})
		for item_code in self.size_item_codes:
			self.assertEqual(self.get_price(item_code, self.default_price_list), 300)

	def test_a_blank_rate_writes_nothing_at_all(self):
		counts = set_variant_prices(self.item_template, default_rate=0, sale_rate=None)

		self.assertEqual(counts, {"created": 0, "updated": 0, "skipped": 0, "queued": 0})
		self.assertFalse(frappe.db.exists("Item Price", {"item_code": self.size_item_codes[0]}))

	def test_a_variant_name_from_another_template_prices_nothing(self):
		# The client sends variant names; a stale or forged one must not reach this template's SKUs.
		foreign_template = self.make_item_template()
		foreign_variant = self.make_style_attribute_variant(
			{"S": self.make_size_item("S", foreign_template)}, item_template=foreign_template
		)

		counts = set_variant_prices(
			self.item_template, default_rate=200, style_attribute_variant_list=[foreign_variant.name]
		)

		self.assertEqual(counts, {"created": 0, "updated": 0, "skipped": 0, "queued": 0})
		self.assertFalse(frappe.db.exists("Item Price", {"price_list": self.default_price_list}))

	def test_only_the_named_variant_gets_priced(self):
		second_variant_item_code = self.make_size_item("L")
		second_variant = self.make_style_attribute_variant({"L": second_variant_item_code})

		counts = set_variant_prices(
			self.item_template, default_rate=200, style_attribute_variant_list=[second_variant.name]
		)

		self.assertEqual(counts["created"], 1)
		self.assertEqual(self.get_price(second_variant_item_code, self.default_price_list), 200)
		self.assertFalse(self.get_price(self.size_item_codes[0], self.default_price_list))

	def test_the_template_item_carries_the_audit_comment(self):
		set_variant_prices(self.item_template, default_rate=200)

		comments = frappe.get_all(
			"Comment",
			filters={"reference_doctype": "Item", "reference_name": self.item_template},
			pluck="content",
		)
		self.assertTrue(any("Bulk pricing by" in comment for comment in comments))


class TestReceiveStock(ProductOnboardingTestCase):
	def test_rejects_an_item_that_is_not_a_size_of_this_variant(self):
		with self.assertRaises(frappe.ValidationError):
			self.variant.receive_stock({self.make_plain_item(): 5})

	def test_rejects_an_all_zero_receipt(self):
		with self.assertRaises(frappe.ValidationError):
			self.variant.receive_stock({self.size_item_codes[0]: 0})

	def test_rejects_a_negative_quantity(self):
		with self.assertRaises(frappe.ValidationError):
			self.variant.receive_stock({self.size_item_codes[0]: -1})

	def test_submits_a_material_receipt_that_get_stock_for_items_can_see(self):
		small, medium = self.size_item_codes

		stock_entry_name = self.variant.receive_stock({small: 7, medium: 0}, {small: 25})

		stock_entry = frappe.get_doc("Stock Entry", stock_entry_name)
		self.assertEqual(stock_entry.docstatus, 1)
		self.assertEqual(stock_entry.stock_entry_type, "Material Receipt")
		self.assertEqual(len(stock_entry.items), 1)
		self.assertEqual(stock_entry.items[0].item_code, small)
		self.assertEqual(stock_entry.items[0].qty, 7)
		self.assertEqual(stock_entry.items[0].t_warehouse, self.warehouse)

		stock_by_item_code = get_stock_for_items([small, medium])
		self.assertEqual(stock_by_item_code[small], 7)
		self.assertEqual(stock_by_item_code[medium], 0)


class TestUpdateProduct(ProductOnboardingTestCase):
	def test_a_blank_title_is_refused_rather_than_ignored(self):
		original_title = frappe.db.get_value("Item", self.item_template, "item_name")

		for blank in ("", "   "):
			with self.subTest(title=blank):
				with self.assertRaises(frappe.ValidationError):
					update_product(self.item_template, title=blank)

		self.assertEqual(frappe.db.get_value("Item", self.item_template, "item_name"), original_title)

	def test_the_framework_would_have_kept_the_old_title_without_complaining(self):
		"""Item backfills a blank item_name from the item_code, so a cleared title reports success silently."""
		item = frappe.get_doc("Item", self.item_template)
		item.item_name = "Cotton Shirt"
		item.save()

		item.item_name = ""
		item.save()

		self.assertEqual(item.item_name, self.item_template)

	def test_a_real_title_still_saves_trimmed(self):
		update_product(self.item_template, title="  Cotton Shirt  ")

		self.assertEqual(frappe.db.get_value("Item", self.item_template, "item_name"), "Cotton Shirt")

	def test_an_omitted_title_leaves_the_stored_one_alone(self):
		update_product(self.item_template, title="Cotton Shirt")

		update_product(self.item_template, description="Soft and light")

		self.assertEqual(frappe.db.get_value("Item", self.item_template, "item_name"), "Cotton Shirt")


class TestRunningLowPanel(ProductOnboardingTestCase):
	"""Home's "Running low" panel and the Inventory screen's low filter have to be one list."""

	def setUp(self):
		super().setUp()
		self.well_stocked_item_code, self.running_low_item_code = self.size_item_codes
		self.variant.receive_stock({self.well_stocked_item_code: LOW_STOCK_THRESHOLD + 20})
		self.variant.receive_stock({self.running_low_item_code: 1})

	def get_item_codes(self, **filters):
		return {row["item_code"] for row in get_inventory(page_length=1000, **filters)["rows"]}

	def test_every_panel_row_is_actually_running_low(self):
		panel = get_overview()["running_low"]

		for row in panel:
			with self.subTest(item_code=row["item_code"]):
				self.assertEqual(row["availability"], "Low")
				self.assertLessEqual(row["stock"], LOW_STOCK_THRESHOLD)
				self.assertGreater(row["stock"], 0)

	def test_the_panel_never_lists_a_size_the_inventory_screen_does_not(self):
		low_item_codes = self.get_item_codes(availability="low")

		for row in get_overview()["running_low"]:
			with self.subTest(item_code=row["item_code"]):
				self.assertIn(row["item_code"], low_item_codes)

	def test_a_well_stocked_size_is_on_the_inventory_screen_but_never_running_low(self):
		self.assertIn(self.well_stocked_item_code, self.get_item_codes())
		self.assertNotIn(self.well_stocked_item_code, self.get_item_codes(availability="low"))

		panel_item_codes = {row["item_code"] for row in get_overview()["running_low"]}
		self.assertNotIn(self.well_stocked_item_code, panel_item_codes)

	def test_a_size_just_under_the_threshold_is_what_the_low_filter_is_for(self):
		self.assertIn(self.running_low_item_code, self.get_item_codes(availability="low"))


class TestCreateProduct(ProductOnboardingTestCase):
	def setUp(self):
		super().setUp()
		self.colour_attribute = self.make_named_attribute("Colour", ["Crimson", "Teal"])
		# Must be the attribute literally named "Size": generate_variants() lowercases it into the
		# Color Size Item fieldname. Shared, so values it lacks are appended and rolled back with the test.
		self.size_attribute = "Size"

	def make_named_attribute(self, label, values):
		attribute = frappe.new_doc("Item Attribute")
		attribute.attribute_name = f"Onboarding {label} {self.suffix}"
		for value in values:
			attribute.append("item_attribute_values", {"attribute_value": value, "abbr": value[:3].upper()})
		attribute.insert()
		return attribute.name

	def add_product(self, option_sizes):
		return create_product(
			title=f"Onboarding Product {frappe.generate_hash(length=6).upper()}",
			collection=self.item_group,
			option_attribute=self.colour_attribute,
			size_attribute=self.size_attribute,
			option_sizes=option_sizes,
		)

	def get_sizes_by_option(self, item_template):
		return {
			variant["option"]: sorted(size["size"] for size in variant["sizes"])
			for variant in get_product(item_template)["variants"]
		}

	def test_a_colour_only_gets_the_sizes_it_is_stocked_in(self):
		product = self.add_product(
			[
				{"option": "Crimson", "sizes": ["S", "M", "L"]},
				{"option": "Teal", "sizes": ["M"]},
			]
		)

		self.assertEqual(
			self.get_sizes_by_option(product["name"]),
			{"Crimson": ["L", "M", "S"], "Teal": ["M"]},
		)
		# The full grid would be six. The two Teal sizes nobody stocks must not exist as Items at all.
		self.assertEqual(frappe.db.count("Item", {"variant_of": product["name"]}), 4)

	def test_a_colour_with_no_sizes_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.add_product([{"option": "Crimson", "sizes": ["S"]}, {"option": "Teal", "sizes": []}])

	def test_one_colour_spelled_two_ways_stays_one_colour(self):
		# ERPNext matches attribute values case-insensitively, so the second pass would collide.
		product = self.add_product(
			[{"option": "Crimson", "sizes": ["S"]}, {"option": "crimson", "sizes": ["M"]}]
		)

		self.assertEqual(self.get_sizes_by_option(product["name"]), {"Crimson": ["M", "S"]})

	def test_option_sizes_accepts_a_json_string(self):
		product = self.add_product(frappe.as_json([{"option": "Teal", "sizes": ["S"]}]))

		self.assertEqual(self.get_sizes_by_option(product["name"]), {"Teal": ["S"]})

	def test_a_colour_the_owner_typed_joins_the_attribute(self):
		product = self.add_product([{"option": "Saffron", "sizes": ["S"]}])

		self.assertIn("Saffron", [row["value"] for row in get_attribute_values(self.colour_attribute)])
		self.assertEqual(self.get_sizes_by_option(product["name"]), {"Saffron": ["S"]})

	def test_get_attribute_values_keeps_the_stored_order(self):
		# Deliberately not alphabetical, and on an attribute this run owns — the shared "Size"
		# attribute carries whatever values other products have added to it.
		stored_order = ["Medium", "Alpha", "Zulu"]
		attribute = self.make_named_attribute("Order", stored_order)

		self.assertEqual([row["value"] for row in get_attribute_values(attribute)], stored_order)


class TestCreateSingleItemProduct(ProductOnboardingTestCase):
	"""A book has neither a colour nor a size. Both axes are still written underneath — see the note
	above DEFAULT_OPTION_VALUE in api/admin/catalog.py."""

	def setUp(self):
		super().setUp()
		self.format_attribute = self.make_named_attribute("Format", ["Paperback", "Hardcover"])

	def make_named_attribute(self, label, values):
		attribute = frappe.new_doc("Item Attribute")
		attribute.attribute_name = f"Onboarding {label} {self.suffix}"
		for value in values:
			attribute.append("item_attribute_values", {"attribute_value": value, "abbr": value[:3].upper()})
		attribute.insert()
		return attribute.name

	def get_sizes_by_option(self, item_template):
		return {
			variant["option"]: sorted(size["size"] for size in variant["sizes"])
			for variant in get_product(item_template)["variants"]
		}

	def add_book(self, **kwargs):
		kwargs.setdefault("title", f"Onboarding Book {frappe.generate_hash(length=6).upper()}")
		kwargs.setdefault("collection", self.item_group)
		return create_product(**kwargs)

	def test_a_book_sold_in_two_formats_gets_one_hidden_size_per_format(self):
		book = self.add_book(
			option_attribute=self.format_attribute,
			option_sizes=[{"option": "Paperback"}, {"option": "Hardcover"}],
		)

		self.assertEqual(
			self.get_sizes_by_option(book["name"]),
			{"Paperback": [DEFAULT_SIZE_VALUE], "Hardcover": [DEFAULT_SIZE_VALUE]},
		)

	def test_a_book_with_no_options_at_all_falls_back_to_a_single_hidden_axis(self):
		book = self.add_book()

		self.assertEqual(self.get_sizes_by_option(book["name"]), {DEFAULT_OPTION_VALUE: [DEFAULT_SIZE_VALUE]})
		self.assertTrue(frappe.db.exists("Item Attribute", DEFAULT_OPTION_ATTRIBUTE))

	def test_the_leaf_item_carries_a_real_size_attribute_row(self):
		"""www/cart/checkout.py filters cart lines on attribute == "Size". A leaf Item without that
		row does not error — it silently vanishes from the shopper's own checkout page."""
		book = self.add_book(option_attribute=self.format_attribute, option_sizes=[{"option": "Paperback"}])

		leaf_item_codes = frappe.get_all("Item", filters={"variant_of": book["name"]}, pluck="name")
		self.assertEqual(len(leaf_item_codes), 1)
		self.assertEqual(
			frappe.db.get_value(
				"Item Variant Attribute",
				{"parent": leaf_item_codes[0], "attribute": SIZE_ATTRIBUTE},
				"attribute_value",
			),
			DEFAULT_SIZE_VALUE,
		)

	def test_the_leaf_item_is_sellable_rather_than_a_template(self):
		"""ERPNext refuses a has_variants template on a Quotation, so the cart's item_code must be
		the leaf — api/payments.py reads it straight off the cart line."""
		book = self.add_book(option_attribute=self.format_attribute, option_sizes=[{"option": "Paperback"}])

		leaf_item_code = frappe.get_all("Item", filters={"variant_of": book["name"]}, pluck="name")[0]
		self.assertFalse(frappe.db.get_value("Item", leaf_item_code, "has_variants"))
		self.assertTrue(frappe.db.get_value("Item", book["name"], "has_variants"))

	def test_a_sizeless_product_has_nothing_blocking_publication_but_its_image(self):
		"""An empty sizes table unpublishes the variant on its own (unpublish_if_incomplete_data),
		so the hidden size has to satisfy the publish blockers too."""
		book = self.add_book(option_attribute=self.format_attribute, option_sizes=[{"option": "Paperback"}])

		blockers = get_product(book["name"])["variants"][0]["blockers"]
		self.assertEqual(blockers, ["Add at least one image"])

	def test_a_half_filled_size_grid_is_still_the_owner_forgetting_a_row(self):
		with self.assertRaises(frappe.ValidationError):
			self.add_book(
				option_attribute=self.format_attribute,
				option_sizes=[{"option": "Paperback", "sizes": ["S"]}, {"option": "Hardcover"}],
			)
