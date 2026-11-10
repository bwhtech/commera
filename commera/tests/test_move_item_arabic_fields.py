"""The patch that moves the Item Arabic name and description into Content Translation."""

import csv
import io
from unittest.mock import patch

import frappe
from frappe.core.doctype.file.file import File
from frappe.custom.doctype.custom_field.custom_field import create_custom_field, delete_custom_fields
from frappe.tests import IntegrationTestCase
from frappe.utils import now

from commera.install import TEST_ITEM_GROUP
from commera.localization import CURRENT, register, resolve, translate
from commera.localization.content import get_source_hash
from commera.patches import move_item_arabic_fields_to_content_translation as migration
from commera.sdk import catalog
from commera.tests import get_test_configurator
from commera.tests.test_content_translation import use_storefront_language
from commera.tests.test_localization import use_storefront_languages

PRODUCT = "Style Attribute Variant"
SETTINGS = "Commera Settings"
LANGUAGE_ROW = "Commera Storefront Language"
NAME_FIELD, DESCRIPTION_FIELD = "custom_item_name_ar", "custom_description_ar"
DESCRIPTION = "<p>A linen shirt for warm days.</p>"
ARABIC_NAME = "قميص كتان"
ARABIC_DESCRIPTION = "<p>قميص كتان للأيام الدافئة.</p>"
UNSAFE_DESCRIPTION = '<p onclick="steal()">قميص كتان</p>'
REBUILD = "commera.search.build.enqueue_full_rebuild"


class TestMoveItemArabicFields(IntegrationTestCase):
	"""Adding and dropping the fields is DDL, which commits: every record here is deleted explicitly."""

	def setUp(self):
		self.started = now()
		keep_language_settings(self)
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.suffix = frappe.generate_hash(length=6).upper()
		self.items, self.configurators, self.products = [], [], []
		self.addCleanup(self.delete_records)
		self.addCleanup(drop_fields)
		add_fields()

	def make_plain_item(self, label, **arabic):
		item = frappe.new_doc("Item")
		item.item_code = item.item_name = f"ARABIC-{label}-{self.suffix}"
		item.item_group = TEST_ITEM_GROUP
		item.stock_uom = "Nos"
		item.description = DESCRIPTION
		item.insert()
		frappe.db.set_value("Item", item.name, arabic)
		self.items.append(item.name)
		return item.name

	def make_item(self, label, **arabic):
		"""A template Item with these Arabic values, and the configurator its products hang off."""
		attribute = frappe.db.get_value(
			"Style Attribute Configurator", get_test_configurator(), "item_attribute"
		)
		item = self.make_plain_item(label, **arabic)
		# A product's item_style is fetched from its configurator's template Item.
		configurator = frappe.get_doc(
			{"doctype": "Style Attribute Configurator", "item_template": item, "item_attribute": attribute}
		).insert(ignore_permissions=True)
		self.configurators.append(configurator.name)
		return configurator.name

	def make_product(self, configurator, colour, published=True, sizes=None):
		product = frappe.new_doc(PRODUCT)
		product.configurator = configurator
		item = frappe.db.get_value("Style Attribute Configurator", configurator, "item_template")
		product.attribute_value = f"{colour} {self.suffix}"
		product.display_name = f"Linen Shirt {colour}"
		product.route = f"arabic-{colour.lower()}-{self.suffix.lower()}"
		product.append("images", {"image": "/assets/arabic-test.jpg"})
		for size, item_code in sizes or [("M", item)]:
			product.append("sizes", {"size": size, "item_code": item_code})
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
		for name in self.archive_files():
			frappe.delete_doc("File", name, force=True, ignore_permissions=True)
		frappe.db.delete("Error Log", {"name": ("in", self.archive_logs() or [""])})
		frappe.db.delete(
			"Comment",
			{"reference_doctype": SETTINGS, "reference_name": SETTINGS, "creation": (">=", self.started)},
		)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	def translations(self, product):
		rows = frappe.get_all(
			"Content Translation",
			filters={"reference_doctype": PRODUCT, "reference_name": product, "language": "ar"},
			fields=["reference_field", "translated_value", "source_hash"],
		)
		return {row.reference_field: row for row in rows}

	def archive_files(self):
		filters = {
			"attached_to_doctype": SETTINGS,
			"file_name": ("like", f"{migration.ARCHIVE_PREFIX}%"),
			"creation": (">=", self.started),
		}
		return frappe.get_all("File", filters=filters, pluck="name")

	def archive_logs(self):
		filters = {"method": migration.ARCHIVE_TITLE, "creation": (">=", self.started)}
		return frappe.get_all("Error Log", filters=filters, pluck="name")

	def archived(self):
		"""{item_code: archive row} of this test's Items, from every archive part the patch saved."""
		rows = {}
		for name in self.archive_files():
			rows |= {row["item_code"]: row for row in read_archive(name)}
		return {code: row for code, row in rows.items() if code.endswith(self.suffix)}

	def run_patch(self):
		with patch(REBUILD) as rebuild:
			migration.execute()
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
		# Every value was copied, so nothing is archived.
		self.assertEqual(self.archive_files(), [])
		self.assertFalse(self.archive_logs())

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
		# The Item's own name was not copied over the kept translation, so the archive has it.
		archived = self.archived()
		self.assertEqual(list(archived), [f"ARABIC-KEEP-{self.suffix}"])
		self.assertIn(NAME_FIELD, archived[f"ARABIC-KEEP-{self.suffix}"]["reason"])

	def test_an_item_without_a_product_is_archived_before_the_drop(self):
		loose = self.make_plain_item(
			"LOOSE", **{NAME_FIELD: ARABIC_NAME, DESCRIPTION_FIELD: ARABIC_DESCRIPTION}
		)

		self.run_patch()

		assert_fields_removed(self)
		[name] = self.archive_files()
		archive = frappe.get_doc("File", name)
		self.assertEqual((archive.is_private, archive.attached_to_name), (1, SETTINGS))
		self.assertTrue(archive.file_name.startswith(f"{migration.ARCHIVE_PREFIX}-"))
		row = self.archived()[loose]
		self.assertEqual(list(row), list(migration.ARCHIVE_HEADER))
		self.assertEqual(
			(row["item_name"], row[NAME_FIELD], row[DESCRIPTION_FIELD], row["reason"]),
			(loose, ARABIC_NAME, ARABIC_DESCRIPTION, "no product uses this Item"),
		)
		[log] = [frappe.get_doc("Error Log", name) for name in self.archive_logs()]
		self.assertIn("Content Translation: 1.", log.error)
		self.assertIn(archive.file_name, log.error)

	def test_a_value_that_sanitising_changes_is_archived_raw(self):
		unsafe = self.make_item("UNSAFE", **{DESCRIPTION_FIELD: UNSAFE_DESCRIPTION})
		dirty = self.make_product(unsafe, "Rust")
		saved = self.make_product(self.make_item("SAVED", **{DESCRIPTION_FIELD: UNSAFE_DESCRIPTION}), "Plum")
		# A translation saved earlier holds the same sanitised value the patch would write.
		register(PRODUCT, saved.name, "description", "ar", UNSAFE_DESCRIPTION)
		clean = self.make_product(self.make_item("CLEAN", **{DESCRIPTION_FIELD: ARABIC_DESCRIPTION}), "Teal")

		self.run_patch()

		self.assertEqual(self.translations(dirty.name)["description"].translated_value, "<p>قميص كتان</p>")
		self.assertEqual(self.translations(clean.name)["description"].translated_value, ARABIC_DESCRIPTION)
		archived = self.archived()
		self.assertEqual(sorted(archived), [f"ARABIC-SAVED-{self.suffix}", f"ARABIC-UNSAFE-{self.suffix}"])
		for row in archived.values():
			self.assertEqual(row[DESCRIPTION_FIELD], UNSAFE_DESCRIPTION)
			self.assertEqual(row["reason"], f"{DESCRIPTION_FIELD}: sanitised on copy")

	def test_the_archive_is_saved_in_parts(self):
		loose = [self.make_plain_item(f"PART{index}", **{NAME_FIELD: ARABIC_NAME}) for index in range(3)]

		# Every row fills a part.
		with patch.object(migration, "ARCHIVE_PART_SIZE", 1):
			self.run_patch()

		files = sorted(
			frappe.get_all("File", filters={"name": ("in", self.archive_files())}, pluck="file_name")
		)
		self.assertEqual(len(files), 3)
		self.assertEqual([name.rsplit("-", 1)[1] for name in files], ["1.csv", "2.csv", "3.csv"])
		parts = [[row["item_code"] for row in read_archive(name)] for name in self.archive_files()]
		self.assertEqual(sorted(parts), [[item] for item in loose])
		[log] = [frappe.get_doc("Error Log", name) for name in self.archive_logs()]
		self.assertIn("Content Translation: 3.", log.error)
		for name in files:
			self.assertIn(name, log.error)

	def test_a_failed_archive_save_keeps_the_fields(self):
		self.make_plain_item("FAIL", **{NAME_FIELD: ARABIC_NAME})

		with (
			patch.object(File, "insert", side_effect=frappe.ValidationError("disk full")),
			self.assertRaises(frappe.ValidationError),
		):
			self.run_patch()

		for field in (NAME_FIELD, DESCRIPTION_FIELD):
			self.assertTrue(frappe.db.has_column("Item", field))
			self.assertTrue(frappe.db.exists("Custom Field", {"dt": "Item", "fieldname": field}))
		self.assertEqual(self.archive_files(), [])

	def test_a_size_item_is_archived_only_when_it_differs_from_its_template(self):
		item = self.make_item("TPL", **{NAME_FIELD: ARABIC_NAME, DESCRIPTION_FIELD: ARABIC_DESCRIPTION})
		same = self.make_plain_item(
			"SAME", **{NAME_FIELD: ARABIC_NAME, DESCRIPTION_FIELD: ARABIC_DESCRIPTION}
		)
		other = self.make_plain_item("OTHER", **{NAME_FIELD: "قميص كبير"})
		self.make_product(item, "Sand", sizes=[("S", same), ("L", other)])

		self.run_patch()

		archived = self.archived()
		self.assertEqual(list(archived), [other])
		self.assertEqual((archived[other][NAME_FIELD], archived[other][DESCRIPTION_FIELD]), ("قميص كبير", ""))
		template = frappe.db.get_value("Style Attribute Configurator", item, "item_template")
		self.assertEqual(archived[other]["reason"], f"{NAME_FIELD} differs from template {template}")

	def test_items_are_read_and_copied_one_page_at_a_time(self):
		products = [
			self.make_product(self.make_item(f"PAGE{index}", **{NAME_FIELD: ARABIC_NAME}), f"Page{index}")
			for index in range(3)
		]
		pages = []
		migrate = migration.ItemArabicMigration.migrate

		def record(run, items):
			pages.append(list(items))
			return migrate(run, items)

		with (
			patch.object(migration, "BATCH_SIZE", 1),
			patch.object(migration.ItemArabicMigration, "migrate", record),
		):
			self.run_patch()

		self.assertEqual(len(pages), 3)
		self.assertEqual(pages, sorted(pages))
		for product in products:
			self.assertEqual(self.translations(product.name)["display_name"].translated_value, ARABIC_NAME)

	def test_a_retry_after_the_drop_still_rebuilds_the_index(self):
		item = self.make_item("TWICE", **{NAME_FIELD: ARABIC_NAME})
		product = self.make_product(item, "Navy")
		self.run_patch()
		register(PRODUCT, product.name, "display_name", "ar", "قميص كحلي")

		rebuild = self.run_patch()

		assert_fields_removed(self)
		self.assertEqual(self.translations(product.name)["display_name"].translated_value, "قميص كحلي")
		rebuild.assert_called_once_with(deduplicate=True)

	def test_a_site_without_the_fields_or_arabic_translations_is_left_alone(self):
		drop_fields()
		# Rolled back before delete_records commits, so other Arabic rows survive.
		frappe.db.savepoint("no_arabic")
		self.addCleanup(frappe.db.rollback, save_point="no_arabic")
		frappe.db.delete("Content Translation", {"reference_doctype": PRODUCT, "language": "ar"})

		rebuild = self.run_patch()

		assert_fields_removed(self)
		self.assertFalse(migration.has_arabic_translations())
		self.assertEqual(self.archive_files(), [])
		rebuild.assert_not_called()


def read_archive(name):
	content = frappe.get_doc("File", name).get_content()
	content = content.decode() if isinstance(content, bytes) else content
	return list(csv.DictReader(io.StringIO(content)))


def keep_language_settings(test):
	"""Restore the language settings at the very end: the DDL here commits what a test sets."""
	default = frappe.db.get_single_value(SETTINGS, "default_storefront_language")
	rows = frappe.get_all(LANGUAGE_ROW, filters={"parent": SETTINGS}, fields=["*"], order_by="idx")
	test.addCleanup(restore_language_settings, default, rows)


def restore_language_settings(default, rows):
	frappe.db.delete(LANGUAGE_ROW, {"parent": SETTINGS})
	for row in rows:
		frappe.get_doc({**row, "doctype": LANGUAGE_ROW}).db_insert()
	frappe.db.set_single_value(SETTINGS, "default_storefront_language", default or "", update_modified=False)
	frappe.db.commit()  # nosemgrep: frappe-manual-commit
	frappe.clear_document_cache(SETTINGS, SETTINGS)
	frappe.local.request_cache.clear()


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
