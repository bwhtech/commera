"""The patch that moves the Item Arabic name and description into Content Translation."""

from unittest.mock import patch

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field, delete_custom_fields
from frappe.tests import IntegrationTestCase

from commera.install import TEST_ITEM_GROUP
from commera.localization import CURRENT, register, resolve, translate
from commera.localization.content import get_source_hash
from commera.patches.move_item_arabic_fields_to_content_translation import execute
from commera.sdk import catalog
from commera.tests import get_test_configurator
from commera.tests.test_content_translation import use_storefront_language
from commera.tests.test_localization import use_storefront_languages

PRODUCT = "Style Attribute Variant"
NAME_FIELD, DESCRIPTION_FIELD = "custom_item_name_ar", "custom_description_ar"
DESCRIPTION = "<p>A linen shirt for warm days.</p>"
ARABIC_NAME = "قميص كتان"
ARABIC_DESCRIPTION = "<p>قميص كتان للأيام الدافئة.</p>"
REBUILD = "commera.search.build.enqueue_full_rebuild"


class TestMoveItemArabicFields(IntegrationTestCase):
	"""Adding and dropping the fields is DDL, which commits: every record here is deleted explicitly."""

	def setUp(self):
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.suffix = frappe.generate_hash(length=6).upper()
		self.items, self.configurators, self.products = [], [], []
		self.addCleanup(self.delete_records)
		self.addCleanup(drop_fields)
		add_fields()

	def make_item(self, label, **arabic):
		"""A template Item with these Arabic values, and the configurator its products hang off."""
		attribute = frappe.db.get_value(
			"Style Attribute Configurator", get_test_configurator(), "item_attribute"
		)
		item = frappe.new_doc("Item")
		item.item_code = item.item_name = f"ARABIC-{label}-{self.suffix}"
		item.item_group = TEST_ITEM_GROUP
		item.stock_uom = "Nos"
		item.description = DESCRIPTION
		item.insert()
		frappe.db.set_value("Item", item.name, arabic)
		self.items.append(item.name)
		# A product's item_style is fetched from its configurator's template Item.
		configurator = frappe.get_doc(
			{
				"doctype": "Style Attribute Configurator",
				"item_template": item.name,
				"item_attribute": attribute,
			}
		).insert(ignore_permissions=True)
		self.configurators.append(configurator.name)
		return configurator.name

	def make_product(self, configurator, colour, published=True):
		product = frappe.new_doc(PRODUCT)
		product.configurator = configurator
		item = frappe.db.get_value("Style Attribute Configurator", configurator, "item_template")
		product.attribute_value = f"{colour} {self.suffix}"
		product.display_name = f"Linen Shirt {colour}"
		product.route = f"arabic-{colour.lower()}-{self.suffix.lower()}"
		product.append("images", {"image": "/assets/arabic-test.jpg"})
		product.append("sizes", {"size": "M", "item_code": item})
		product.is_published = int(published)
		product.insert(ignore_permissions=True)
		self.products.append(product.name)
		return product

	def delete_records(self):
		frappe.db.delete("Content Translation", {"reference_name": ("in", self.products or [""])})
		for name in self.products:
			frappe.delete_doc(PRODUCT, name, force=True, ignore_permissions=True)
		for name in self.configurators:
			frappe.delete_doc("Style Attribute Configurator", name, force=True, ignore_permissions=True)
		for name in self.items:
			frappe.delete_doc("Item", name, force=True, ignore_permissions=True)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	def translations(self, product):
		rows = frappe.get_all(
			"Content Translation",
			filters={"reference_doctype": PRODUCT, "reference_name": product, "language": "ar"},
			fields=["reference_field", "translated_value", "source_hash"],
		)
		return {row.reference_field: row for row in rows}

	def run_patch(self):
		with patch(REBUILD) as rebuild:
			execute()
		return rebuild

	def test_every_product_of_the_item_gets_current_arabic_translations(self):
		item = self.make_item("COPY", **{NAME_FIELD: ARABIC_NAME, DESCRIPTION_FIELD: ARABIC_DESCRIPTION})
		red, blue = self.make_product(item, "Red"), self.make_product(item, "Blue", published=False)

		rebuild = self.run_patch()

		for product in (red, blue):
			rows = self.translations(product.name)
			self.assertEqual(rows["display_name"].translated_value, ARABIC_NAME)
			self.assertEqual(rows["display_name"].source_hash, get_source_hash(product.display_name))
			self.assertEqual(rows["description"].translated_value, ARABIC_DESCRIPTION)
			self.assertEqual(rows["description"].source_hash, get_source_hash(DESCRIPTION))
		translated = translate(
			[frappe.get_doc(PRODUCT, red.name)], ["display_name", "description"], resolve("/ar")[0]
		)
		self.assertEqual({value.status for value in translated[0].values()}, {CURRENT})
		rebuild.assert_called_once_with(deduplicate=True)

		use_storefront_language(self, "ar")
		shown = catalog.get_product(red.route)
		self.assertEqual((shown["title"], shown["description_html"]), (ARABIC_NAME, ARABIC_DESCRIPTION))

	def test_existing_translations_stay_and_blank_values_copy_nothing(self):
		item = self.make_item(
			"KEEP", **{NAME_FIELD: ARABIC_NAME, DESCRIPTION_FIELD: "<p>نص <script>alert(1)</script></p>"}
		)
		kept = self.make_product(item, "Green")
		register(PRODUCT, kept.name, "display_name", "ar", "قميص أخضر")
		blank = self.make_product(
			self.make_item("BLANK", **{NAME_FIELD: "  ", DESCRIPTION_FIELD: ""}), "Grey"
		)

		self.run_patch()

		rows = self.translations(kept.name)
		self.assertEqual(rows["display_name"].translated_value, "قميص أخضر")
		# Sanitised as a Content Translation save sanitises it.
		self.assertNotIn("<script", rows["description"].translated_value)
		self.assertEqual(self.translations(blank.name), {})

	def test_the_fields_go_and_a_second_run_changes_nothing(self):
		item = self.make_item("TWICE", **{NAME_FIELD: ARABIC_NAME})
		product = self.make_product(item, "Navy")
		self.run_patch()
		register(PRODUCT, product.name, "display_name", "ar", "قميص كحلي")

		rebuild = self.run_patch()

		assert_fields_removed(self)
		self.assertEqual(self.translations(product.name)["display_name"].translated_value, "قميص كحلي")
		rebuild.assert_not_called()

	def test_a_site_without_the_fields_is_left_alone(self):
		drop_fields()
		count = frappe.db.count("Content Translation")

		rebuild = self.run_patch()

		assert_fields_removed(self)
		self.assertEqual(frappe.db.count("Content Translation"), count)
		rebuild.assert_not_called()


def add_fields():
	create_custom_field("Item", {"fieldname": NAME_FIELD, "label": "Item Name AR", "fieldtype": "Data"})
	create_custom_field(
		"Item", {"fieldname": DESCRIPTION_FIELD, "label": "Description AR", "fieldtype": "Text Editor"}
	)


def drop_fields():
	delete_custom_fields({"Item": [NAME_FIELD, DESCRIPTION_FIELD]})
	if columns := [field for field in (NAME_FIELD, DESCRIPTION_FIELD) if frappe.db.has_column("Item", field)]:
		frappe.db.drop_columns("Item", columns)
		frappe.client_cache.delete_value("table_columns::tabItem")


def assert_fields_removed(test):
	for field in (NAME_FIELD, DESCRIPTION_FIELD):
		test.assertFalse(frappe.db.has_column("Item", field))
		test.assertFalse(frappe.db.exists("Custom Field", {"dt": "Item", "fieldname": field}))
