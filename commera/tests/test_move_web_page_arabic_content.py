"""The patch that moves the Shop Web Page Arabic content into Content Translation."""

import csv
import io
from unittest.mock import patch

import frappe
from frappe.core.doctype.file.file import File
from frappe.custom.doctype.custom_field.custom_field import create_custom_field, delete_custom_fields
from frappe.tests import IntegrationTestCase
from frappe.utils import now
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.localization import register
from commera.localization.content import get_source_hash
from commera.patches import legacy_arabic
from commera.patches import move_web_page_arabic_content_to_content_translation as migration
from commera.tests.test_localization import use_storefront_languages
from commera.tests.test_move_item_arabic_fields import keep_language_settings
from commera.www.shop_web_page import index as www_shop_web_page

PAGE, COLUMN = "Shop Web Page", "content_ar"
SETTINGS = "Commera Settings"
ENGLISH = "<p>Free returns within 30 days.</p>"
ARABIC = "<p>إرجاع مجاني خلال 30 يومًا.</p>"
UNSAFE = '<p onclick="steal()">إرجاع</p>'


class ArabicArchiveTestCase(IntegrationTestCase):
	"""The patches commit, so every record here is deleted explicitly. Subclasses set `migration`."""

	migration = None

	def setUp(self):
		self.started = now()
		keep_language_settings(self)
		use_storefront_languages(self, "en", published=("en", "ar"))
		self.suffix = frappe.generate_hash(length=6).upper()
		self.addCleanup(self.delete_archive)

	def delete_archive(self):
		for name in self.archive_files():
			frappe.delete_doc("File", name, force=True, ignore_permissions=True)
		# Error Log is a virtual doctype stored in the log database, so it is deleted through its controller.
		for name in self.archive_logs():
			frappe.delete_doc("Error Log", name, force=True, ignore_permissions=True)
		frappe.db.delete(
			"Comment",
			{"reference_doctype": SETTINGS, "reference_name": SETTINGS, "creation": (">=", self.started)},
		)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	def archive_files(self):
		filters = {
			"attached_to_doctype": SETTINGS,
			"file_name": ("like", f"{self.migration.ARCHIVE_PREFIX}%"),
			"creation": (">=", self.started),
		}
		return frappe.get_all("File", filters=filters, pluck="name")

	def archive_logs(self):
		filters = {"method": self.migration.ARCHIVE_TITLE, "creation": (">=", self.started)}
		return frappe.get_all("Error Log", filters=filters, pluck="name")

	def archived_rows(self):
		return [row for name in self.archive_files() for row in read_archive(name)]

	def translations(self, doctype, name):
		rows = frappe.get_all(
			"Content Translation",
			filters={"reference_doctype": doctype, "reference_name": name, "language": "ar"},
			fields=["reference_field", "translated_value", "source_hash"],
		)
		return {row.reference_field: row for row in rows}


class TestMoveWebPageArabicContent(ArabicArchiveTestCase):
	migration = migration

	def setUp(self):
		super().setUp()
		self.pages = []
		self.addCleanup(self.delete_pages)
		self.addCleanup(drop_field)
		add_field()

	def make_page(self, label, arabic=None):
		page = frappe.new_doc(PAGE)
		page.name = f"Arabic {label} {self.suffix}"
		page.content = ENGLISH
		page.insert()
		if arabic is not None:
			frappe.db.set_value(PAGE, page.name, COLUMN, arabic)
		self.pages.append(page.name)
		return page

	def delete_pages(self):
		frappe.db.delete("Content Translation", {"reference_name": ("in", self.pages or [""])})
		for name in self.pages:
			frappe.delete_doc(PAGE, name, force=True, ignore_permissions=True)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	def archived(self):
		return {row["page"]: row for row in self.archived_rows() if row["page"].endswith(self.suffix)}

	def render(self, page, lang):
		frappe.local.request = Request(EnvironBuilder(path=f"/{lang}/page/{page.route}").get_environ())
		frappe.form_dict.route = page.route
		self.addCleanup(frappe.form_dict.pop, "route", None)
		frappe.local.request_cache.clear()
		frappe.clear_document_cache(PAGE, page.name)
		context = frappe._dict()
		www_shop_web_page.get_context(context)
		return context.content

	def test_the_content_is_copied_with_the_current_source_hash_and_renders_in_arabic(self):
		keep_request(self)
		page = self.make_page("Copy", ARABIC)

		migration.execute()

		row = self.translations(PAGE, page.name)["content"]
		self.assertEqual((row.translated_value, row.source_hash), (ARABIC, get_source_hash(ENGLISH)))
		self.assertEqual(self.archive_files(), [])
		self.assertFalse(self.archive_logs())
		self.assertEqual(self.render(page, "ar"), ARABIC)
		self.assertEqual(self.render(page, "en"), ENGLISH)

	def test_an_existing_translation_stays_and_the_legacy_value_is_archived(self):
		kept = self.make_page("Kept", ARABIC)
		register(PAGE, kept.name, "content", "ar", "<p>محفوظ</p>")
		same = self.make_page("Same", ARABIC)
		register(PAGE, same.name, "content", "ar", ARABIC)
		blank = self.make_page("Blank", "  ")

		migration.execute()

		self.assertEqual(self.translations(PAGE, kept.name)["content"].translated_value, "<p>محفوظ</p>")
		self.assertEqual(self.translations(PAGE, blank.name), {})
		archived = self.archived()
		self.assertEqual(list(archived), [kept.name])
		self.assertEqual(
			(archived[kept.name]["route"], archived[kept.name][COLUMN], archived[kept.name]["reason"]),
			(kept.route, ARABIC, "a translation was already saved"),
		)
		[log] = [frappe.get_doc("Error Log", name) for name in self.archive_logs()]
		self.assertIn("Content Translation: 1.", log.error)
		self.assertIn(frappe.db.get_value("File", self.archive_files()[0], "file_name"), log.error)

	def test_a_value_that_sanitising_changes_is_archived_raw(self):
		page = self.make_page("Unsafe", UNSAFE)

		migration.execute()

		self.assertEqual(self.translations(PAGE, page.name)["content"].translated_value, "<p>إرجاع</p>")
		archive = frappe.get_doc("File", self.archive_files()[0])
		self.assertEqual((archive.is_private, archive.attached_to_name), (1, SETTINGS))
		row = self.archived()[page.name]
		self.assertEqual(list(row), list(migration.ARCHIVE_HEADER))
		self.assertEqual((row[COLUMN], row["reason"]), (UNSAFE, "sanitised on copy"))

	def test_a_value_the_collation_treats_as_empty_is_still_copied(self):
		# utf8mb4_unicode_ci ignores U+200B, so `!= ""` would skip this page and drop its value.
		page = self.make_page("Invisible", "​")

		migration.execute()

		self.assertEqual(self.translations(PAGE, page.name)["content"].translated_value, "​")

	def test_pages_are_read_one_page_at_a_time_in_name_order(self):
		pages = [self.make_page(f"Batch {index}", ARABIC) for index in range(3)]
		batches = []
		migrate = migration.WebPageArabicMigration.migrate

		def record(run, rows):
			batches.append([row.name for row in rows])
			return migrate(run, rows)

		with (
			patch.object(migration, "BATCH_SIZE", 1),
			patch.object(migration.WebPageArabicMigration, "migrate", record),
		):
			migration.execute()

		ours = [batch for batch in batches if batch[0].endswith(self.suffix)]
		self.assertEqual(ours, [[page.name] for page in sorted(pages, key=lambda page: page.name)])
		self.assertTrue(all(len(batch) == 1 for batch in batches))
		self.assertEqual(batches, sorted(batches))

	def test_the_archive_is_saved_in_parts(self):
		pages = [self.make_page(f"Part {index}", UNSAFE) for index in range(3)]

		# Every row fills a part.
		with patch.object(legacy_arabic, "ARCHIVE_PART_SIZE", 1):
			migration.execute()

		names = frappe.get_all("File", filters={"name": ("in", self.archive_files())}, pluck="file_name")
		self.assertEqual(len(names), len(self.archived_rows()))
		self.assertEqual(sorted(self.archived()), sorted(page.name for page in pages))
		[log] = [frappe.get_doc("Error Log", name) for name in self.archive_logs()]
		for name in names:
			self.assertIn(name, log.error)

	def test_a_failed_archive_save_keeps_the_field(self):
		self.make_page("Fail", UNSAFE)

		with (
			patch.object(File, "insert", side_effect=frappe.ValidationError("disk full")),
			self.assertRaises(frappe.ValidationError),
		):
			migration.execute()

		self.assertTrue(frappe.db.has_column(PAGE, COLUMN))
		self.assertTrue(frappe.db.exists("Custom Field", {"dt": PAGE, "fieldname": COLUMN}))
		self.assertEqual(self.archive_files(), [])

	def test_the_field_is_removed_and_a_second_run_does_nothing(self):
		page = self.make_page("Twice", ARABIC)
		migration.execute()
		assert_field_removed(self)
		register(PAGE, page.name, "content", "ar", "<p>جديد</p>")

		migration.execute()

		assert_field_removed(self)
		self.assertEqual(self.translations(PAGE, page.name)["content"].translated_value, "<p>جديد</p>")
		self.assertEqual(self.archive_files(), [])

	def test_a_site_without_the_field_is_left_alone(self):
		drop_field()
		page = self.make_page("Absent")

		migration.execute()

		assert_field_removed(self)
		self.assertEqual(self.translations(PAGE, page.name), {})
		self.assertEqual(self.archive_files(), [])


def keep_request(test):
	test.addCleanup(setattr, frappe.local, "request", getattr(frappe.local, "request", None))
	test.addCleanup(setattr, frappe.local, "lang", frappe.local.lang)
	test.addCleanup(frappe.local.request_cache.clear)


def read_archive(name):
	content = frappe.get_doc("File", name).get_content()
	content = content.decode() if isinstance(content, bytes) else content
	return list(csv.DictReader(io.StringIO(content)))


def add_field():
	create_custom_field(PAGE, {"fieldname": COLUMN, "label": "Content (Arabic)", "fieldtype": "Text Editor"})


def drop_field():
	delete_custom_fields({PAGE: [COLUMN]})
	if frappe.db.has_column(PAGE, COLUMN):
		frappe.db.drop_columns(PAGE, [COLUMN])
		frappe.client_cache.delete_value(f"table_columns::tab{PAGE}")
	frappe.clear_cache(doctype=PAGE)


def assert_field_removed(test):
	test.assertFalse(frappe.db.has_column(PAGE, COLUMN))
	test.assertFalse(frappe.db.exists("Custom Field", {"dt": PAGE, "fieldname": COLUMN}))
