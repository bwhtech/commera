from unittest.mock import patch

import frappe
from erpnext.controllers.item_variant import create_variant
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

from commera import erpnext_import
from commera.api.admin.catalog import (
	DEFAULT_OPTION_VALUE,
	DEFAULT_SIZE_VALUE,
	SIZE_ATTRIBUTE,
	add_missing_attribute_values,
	create_product,
	ensure_attribute_exists,
	get_products,
	save_product_options,
)
from commera.api.admin.erpnext_import import (
	get_erpnext_import_preview,
	get_erpnext_import_status,
	publish_imported_products,
	start_erpnext_import,
)
from commera.commera_ecommerce.doctype.commera_settings.commera_settings import create_configurator_log
from commera.sdk.lines import LineProducts
from commera.swatches import COLOUR_ATTRIBUTE
from commera.tests.test_admin_orders import COMPANY, CURRENCY
from commera.tests.test_product_onboarding import ProductOnboardingTestCase
from commera.www.cart.checkout import get_checkout_items


class TestErpnextImport(ProductOnboardingTestCase):
	def setUp(self):
		super().setUp()
		ensure_attribute_exists(COLOUR_ATTRIBUTE, "Red", "RED")
		ensure_attribute_exists(SIZE_ATTRIBUTE, DEFAULT_SIZE_VALUE, "OS")
		add_missing_attribute_values(COLOUR_ATTRIBUTE, ["Red", "Blue"])
		add_missing_attribute_values(SIZE_ATTRIBUTE, ["S", "M"])
		self.material = self.make_attribute("Material", ["Cotton", "Linen"])
		self.storage = self.make_attribute("Storage", ["64 GB", "128 GB"])

	def make_attribute(self, label, values):
		attribute = frappe.new_doc("Item Attribute")
		attribute.attribute_name = f"Import {label} {self.suffix}"
		for value in values:
			attribute.append("item_attribute_values", {"attribute_value": value, "abbr": value[:3].upper()})
		attribute.insert()
		return attribute.name

	def make_template(self, attributes, combinations, image=None):
		item = frappe.new_doc("Item")
		item.item_code = f"IMPORT-{frappe.generate_hash(length=8).upper()}"
		item.item_name = item.item_code
		item.item_group = self.item_group
		item.stock_uom = "Nos"
		item.has_variants = 1
		item.variant_based_on = "Item Attribute"
		item.image = image
		for attribute in attributes:
			item.append("attributes", {"attribute": attribute})
		item.insert()
		variants = [create_variant(item.name, combination).insert() for combination in combinations]
		return item.name, [variant.name for variant in variants]

	def run_import(self, item_codes):
		log = create_configurator_log()
		with patch.object(frappe.db, "commit"):
			erpnext_import.import_items(item_codes, log.name, import_id=f"test-{self.suffix}")
		return log.name, erpnext_import.get_status(f"test-{self.suffix}")

	def get_options(self, item_template):
		variants = frappe.get_all(
			"Style Attribute Variant",
			filters={"item_style": item_template},
			fields=["name", "attribute_value", "is_published"],
		)
		sizes = frappe.get_all(
			"Color Size Item",
			filters={
				"parent": ["in", [row.name for row in variants]],
				"parenttype": "Style Attribute Variant",
			},
			fields=["parent", "size", "item_code"],
		)
		option_by_variant = {row.name: row.attribute_value for row in variants}
		options = {}
		for row in sizes:
			options.setdefault(option_by_variant[row.parent], set()).add((row.size, row.item_code))
		return options

	def make_quotation(self, item_code):
		quotation = frappe.new_doc("Quotation")
		quotation.quotation_to = "Customer"
		customer = frappe.new_doc("Customer")
		customer.customer_name = f"Import Shopper {frappe.generate_hash(length=8)}"
		customer.insert(ignore_permissions=True)
		quotation.party_name = customer.name
		quotation.company = COMPANY
		quotation.currency = CURRENCY
		quotation.conversion_rate = 1
		quotation.append("items", {"item_code": item_code, "qty": 1, "rate": 499})
		quotation.flags.ignore_permissions = True
		quotation.insert()
		return quotation

	def test_each_kind_imports_with_its_option_and_size_labels(self):
		plain = self.make_plain_item()
		colour_size, (red_small, red_medium, blue_small, disabled) = self.make_template(
			[COLOUR_ATTRIBUTE, SIZE_ATTRIBUTE],
			[
				{COLOUR_ATTRIBUTE: "Red", SIZE_ATTRIBUTE: "S"},
				{COLOUR_ATTRIBUTE: "Red", SIZE_ATTRIBUTE: "M"},
				{COLOUR_ATTRIBUTE: "Blue", SIZE_ATTRIBUTE: "S"},
				{COLOUR_ATTRIBUTE: "Blue", SIZE_ATTRIBUTE: "M"},
			],
		)
		frappe.db.set_value("Item", disabled, "disabled", 1)
		size_only, (small, medium) = self.make_template(
			[SIZE_ATTRIBUTE], [{SIZE_ATTRIBUTE: "S"}, {SIZE_ATTRIBUTE: "M"}]
		)
		colour_only, (red, blue) = self.make_template(
			[COLOUR_ATTRIBUTE], [{COLOUR_ATTRIBUTE: "Red"}, {COLOUR_ATTRIBUTE: "Blue"}]
		)
		other, (cotton_64, cotton_128) = self.make_template(
			[self.material, self.storage],
			[
				{self.material: "Cotton", self.storage: "64 GB"},
				{self.material: "Cotton", self.storage: "128 GB"},
			],
		)

		_log, status = self.run_import([plain, colour_size, size_only, colour_only, other])

		self.assertEqual((status["status"], status["created"], status["failed"]), ("done", 5, []))
		self.assertEqual(self.get_options(plain), {DEFAULT_OPTION_VALUE: {(DEFAULT_SIZE_VALUE, plain)}})
		self.assertEqual(
			self.get_options(colour_size),
			{"Red": {("S", red_small), ("M", red_medium)}, "Blue": {("S", blue_small)}},
		)
		self.assertEqual(self.get_options(size_only), {DEFAULT_OPTION_VALUE: {("S", small), ("M", medium)}})
		self.assertEqual(
			self.get_options(colour_only),
			{"Red": {(DEFAULT_SIZE_VALUE, red)}, "Blue": {(DEFAULT_SIZE_VALUE, blue)}},
		)
		self.assertEqual(self.get_options(other), {"Cotton": {("64 GB", cotton_64), ("128 GB", cotton_128)}})

	def test_an_imported_variant_line_is_titled_like_the_product(self):
		template, (red_small,) = self.make_template(
			[COLOUR_ATTRIBUTE, SIZE_ATTRIBUTE], [{COLOUR_ATTRIBUTE: "Red", SIZE_ATTRIBUTE: "S"}]
		)
		frappe.db.set_value("Item", template, "item_name", "Field Hoodie")
		item_name = frappe.db.get_value("Item", red_small, "item_name")
		self.run_import([template])

		self.assertEqual(
			LineProducts([red_small]).get_order_title(red_small, item_name), "Field Hoodie - Red - S"
		)

	def test_an_imported_plain_item_line_reads_its_name(self):
		plain = self.make_plain_item()
		self.run_import([plain])

		self.assertEqual(LineProducts([plain]).get_order_title(plain, plain), plain)

	def test_a_commera_variant_line_keeps_its_item_name(self):
		item_template = create_product(
			title=f"Line Title {self.suffix}",
			collection=self.item_group,
			option_attribute=COLOUR_ATTRIBUTE,
			size_attribute=SIZE_ATTRIBUTE,
			option_sizes=[{"option": "Red", "sizes": ["S"]}, {"option": "Blue", "sizes": ["M"]}],
		)["name"]
		item_codes = frappe.get_all("Item", filters={"variant_of": item_template}, pluck="name")
		products = LineProducts(item_codes)

		for item_code in item_codes:
			item_name = frappe.db.get_value("Item", item_code, "item_name")
			self.assertEqual(products.get_order_title(item_code, item_name), item_name)

	def test_a_colour_and_size_template_with_another_attribute_keeps_it_in_the_size_label(self):
		template, (small_cotton, small_linen) = self.make_template(
			[COLOUR_ATTRIBUTE, SIZE_ATTRIBUTE, self.material],
			[
				{COLOUR_ATTRIBUTE: "Red", SIZE_ATTRIBUTE: "S", self.material: "Cotton"},
				{COLOUR_ATTRIBUTE: "Red", SIZE_ATTRIBUTE: "S", self.material: "Linen"},
			],
		)

		self.run_import([template])

		self.assertEqual(
			self.get_options(template), {"Red": {("S / Cotton", small_cotton), ("S / Linen", small_linen)}}
		)

	def test_preview_lists_kinds_and_skips_manufacturer_templates(self):
		colour_only, _variants = self.make_template([COLOUR_ATTRIBUTE], [{COLOUR_ATTRIBUTE: "Red"}])
		manufacturer = frappe.new_doc("Item")
		manufacturer.item_code = f"IMPORT-MFR-{self.suffix}"
		manufacturer.item_group = self.item_group
		manufacturer.stock_uom = "Nos"
		manufacturer.has_variants = 1
		manufacturer.variant_based_on = "Manufacturer"
		manufacturer.insert()

		preview = get_erpnext_import_preview(search="IMPORT-")

		kinds = {row["item_code"]: (row["kind"], row["preselected"]) for row in preview["items"]}
		self.assertEqual(kinds[colour_only], ("colour_only", True))
		self.assertNotIn(manufacturer.name, kinds)
		self.assertIn(manufacturer.name, [row["item_code"] for row in preview["skipped"]])

	def test_import_never_adds_items_prices_or_stock(self):
		plain = self.make_plain_item()
		template, _variants = self.make_template([SIZE_ATTRIBUTE], [{SIZE_ATTRIBUTE: "S"}])
		counts_before = [frappe.db.count(doctype) for doctype in ("Item", "Item Price", "Bin")]

		self.run_import([plain, template])

		self.assertEqual(
			[frappe.db.count(doctype) for doctype in ("Item", "Item Price", "Bin")], counts_before
		)

	def test_products_list_shows_imports_with_price_and_stock(self):
		plain = self.make_plain_item()
		self.price_item(plain)
		make_stock_entry(item_code=plain, qty=3, to_warehouse=self.warehouse, rate=100)

		self.run_import([plain])

		product = {row["name"]: row for row in get_products(search=plain)["products"]}[plain]
		self.assertEqual((product["price_from"], product["stock"]), (499, 3))

	def test_a_second_run_imports_nothing_new(self):
		plain = self.make_plain_item()
		self.run_import([plain])

		_log, status = self.run_import([plain])

		self.assertEqual((status["created"], status["skipped"]), (0, 1))
		self.assertEqual(frappe.db.count("Style Attribute Configurator", {"item_template": plain}), 1)

	def test_one_bad_template_fails_alone(self):
		good, bad = self.make_plain_item(), self.make_plain_item()
		add_product = erpnext_import.add_product

		def fail_after_writing(plan):
			configurator = add_product(plan)
			if plan["item_code"] == bad:
				frappe.throw("Broken template")
			return configurator

		with patch.object(erpnext_import, "add_product", fail_after_writing):
			_log, status = self.run_import([good, bad])

		self.assertEqual(status["created"], 1)
		item_name = frappe.db.get_value("Item", bad, "item_name")
		self.assertEqual(
			status["failed"], [{"item_code": bad, "item_name": item_name, "error": "Broken template"}]
		)
		self.assertTrue(frappe.db.exists("Style Attribute Configurator", {"item_template": good}))
		self.assertFalse(frappe.db.exists("Style Attribute Configurator", {"item_template": bad}))

	def test_an_unexpected_failure_is_logged_and_told_in_plain_words(self):
		bad = self.make_plain_item()

		def crash(plan):
			raise AttributeError("'NoneType' object has no attribute 'name'")

		with (
			patch.object(erpnext_import, "add_product", crash),
			patch.object(erpnext_import.frappe, "log_error") as log_error,
		):
			_log, status = self.run_import([bad])

		self.assertEqual(
			status["failed"][0]["error"], "Something went wrong with this item. Run the import again to retry it."
		)
		log_error.assert_called_once()

	def price_item(self, item_code, rate=499):
		item_price = frappe.new_doc("Item Price")
		item_price.item_code = item_code
		item_price.price_list = self.default_price_list
		item_price.price_list_rate = rate
		item_price.insert()

	def test_publish_all_publishes_products_with_and_without_a_photo(self):
		with_photo = self.make_plain_item()
		frappe.db.set_value("Item", with_photo, "image", self.make_file())
		without_photo = self.make_plain_item()
		for item_code in (with_photo, without_photo):
			self.price_item(item_code)
		log, _status = self.run_import([with_photo, without_photo])

		result = publish_imported_products(log)

		self.assertEqual(result["published"], 2)
		self.assertEqual(result["not_published"], [])
		self.assertEqual(
			frappe.db.get_value("Style Attribute Variant", {"item_style": without_photo}, "is_published"), 1
		)

	def test_publish_all_leaves_an_unpriced_item_as_a_draft_and_says_why(self):
		"""Publish all goes through catalog.get_publish_blockers, like every other publish path."""
		priced, unpriced = self.make_plain_item(), self.make_plain_item()
		self.price_item(priced)
		log, _status = self.run_import([priced, unpriced])

		result = publish_imported_products(log)

		self.assertEqual(result["published"], 1)
		self.assertEqual(
			result["not_published"],
			[{"item_template": unpriced, "title": unpriced, "reasons": ["Add a price before publishing"]}],
		)
		self.assertEqual(
			frappe.db.get_value("Style Attribute Variant", {"item_style": unpriced}, "is_published"), 0
		)

	def test_an_imported_plain_item_reaches_checkout(self):
		plain = self.make_plain_item()
		self.run_import([plain])

		lines = get_checkout_items(self.make_quotation(plain))

		self.assertEqual([(line.item_code, line.size) for line in lines], [(plain, DEFAULT_SIZE_VALUE)])

	def test_starting_while_an_import_runs_answers_with_the_running_one(self):
		item_code = self.make_plain_item()
		erpnext_import.set_status(
			erpnext_import.JOB_ID, erpnext_import.get_new_progress("running", "RUNNING-LOG")
		)
		self.addCleanup(frappe.cache.delete_value, erpnext_import.status_key(erpnext_import.JOB_ID))

		with patch.object(erpnext_import, "is_job_enqueued", return_value=True):
			started = start_erpnext_import([item_code])

		self.assertEqual(started, {"job_id": erpnext_import.JOB_ID, "log": "RUNNING-LOG"})

	def test_a_dead_job_reads_as_failed(self):
		erpnext_import.set_status(f"dead-{self.suffix}", erpnext_import.get_new_progress("running", "LOG"))

		self.assertEqual(get_erpnext_import_status(f"dead-{self.suffix}")["status"], "failed")

	def test_start_needs_the_store_settings(self):
		with patch.object(erpnext_import, "get_missing_settings", return_value=["Ecommerce Warehouse"]):
			with self.assertRaisesRegex(frappe.ValidationError, "Ecommerce Warehouse"):
				start_erpnext_import()

	def test_editing_options_of_an_imported_size_only_product_is_refused(self):
		template, _variants = self.make_template([SIZE_ATTRIBUTE], [{SIZE_ATTRIBUTE: "S"}])
		self.run_import([template])

		with self.assertRaisesRegex(frappe.ValidationError, "in ERPNext"):
			save_product_options(template, add=[{"option": DEFAULT_OPTION_VALUE, "size": "M"}])
