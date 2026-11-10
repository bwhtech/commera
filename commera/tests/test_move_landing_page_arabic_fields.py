"""The patch that moves the Landing Page Settings Arabic fields into Content Translation."""

from unittest.mock import patch

import frappe
from frappe.core.doctype.file.file import File
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from commera.localization import register
from commera.localization.content import get_source_hash
from commera.patches import move_landing_page_arabic_fields_to_content_translation as migration
from commera.tests.test_move_web_page_arabic_content import ArabicArchiveTestCase, keep_request
from commera.www import index as homepage

LANDING_PAGE, BANNER = "Landing Page Settings", "Landing Page Hero Banner"
ENGLISH = {"gif_1": "/files/en-gif-1.gif", "gif_url_1": "/collections/en", "banner_1": "/files/en-banner.jpg"}
ARABIC = {"gif_1_ar": "/files/ar-gif-1.gif", "gif_url_1_ar": "/collections/ar", "banner_url_1_ar": "/ar-sale"}
ENGLISH_BANNERS = [("/files/en-hero-1.jpg", "/en-1"), ("/files/en-hero-2.jpg", "/en-2")]


class TestMoveLandingPageArabicFields(ArabicArchiveTestCase):
	migration = migration

	def setUp(self):
		super().setUp()
		keep_landing_page(self)
		self.addCleanup(self.delete_translations)
		clear_landing_page()
		for field, value in ENGLISH.items():
			write_single(field, value)
		self.english_banners = [
			add_banner("hero_banner", index, image, url)
			for index, (image, url) in enumerate(ENGLISH_BANNERS, start=1)
		]

	def delete_translations(self):
		frappe.db.delete(
			"Content Translation",
			{"reference_doctype": ("in", [LANDING_PAGE, BANNER]), "creation": (">=", self.started)},
		)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	def add_arabic(self, banners=()):
		for field, value in ARABIC.items():
			write_single(field, value)
		for index, (image, url) in enumerate(banners, start=1):
			add_banner(migration.TABLE, index, image, url)

	def homepage(self, lang):
		frappe.local.request = Request(EnvironBuilder(path=f"/{lang}/").get_environ())
		frappe.local.request_cache.clear()
		frappe.clear_document_cache(LANDING_PAGE, LANDING_PAGE)
		return homepage.get_homepage_details()

	def test_values_and_banners_are_copied_and_the_homepage_shows_them_in_arabic(self):
		keep_request(self)
		self.add_arabic(banners=[("/files/ar-hero-1.jpg", "/ar-1")])

		migration.execute()

		rows = self.translations(LANDING_PAGE, LANDING_PAGE)
		self.assertEqual(
			{field: row.translated_value for field, row in rows.items()},
			{"gif_1": "/files/ar-gif-1.gif", "gif_url_1": "/collections/ar", "banner_url_1": "/ar-sale"},
		)
		self.assertEqual(rows["gif_1"].source_hash, get_source_hash(ENGLISH["gif_1"]))
		source = frappe.db.get_single_value(LANDING_PAGE, "banner_url_1")
		self.assertEqual(rows["banner_url_1"].source_hash, get_source_hash(source))
		banner = self.translations(BANNER, self.english_banners[0])
		self.assertEqual(banner["url"].source_hash, get_source_hash("/en-1"))
		self.assertEqual(self.translations(BANNER, self.english_banners[1]), {})
		self.assertEqual(self.archive_files(), [])
		assert_fields_removed(self)

		arabic = self.homepage("ar")
		self.assertEqual(
			(arabic.gif_1, arabic.gif_url_1, arabic.banner_1, arabic.banner_url_1),
			("/files/ar-gif-1.gif", "/collections/ar", "/files/en-banner.jpg", "/ar-sale"),
		)
		self.assertEqual(
			[(row.banner_image, row.url) for row in arabic.hero_banner],
			[("/files/ar-hero-1.jpg", "/ar-1"), ENGLISH_BANNERS[1]],
		)
		english = self.homepage("en")
		self.assertEqual((english.gif_1, english.gif_url_1), (ENGLISH["gif_1"], ENGLISH["gif_url_1"]))
		self.assertEqual([(row.banner_image, row.url) for row in english.hero_banner], ENGLISH_BANNERS)

	def test_extra_arabic_banners_and_kept_translations_are_archived(self):
		register(LANDING_PAGE, LANDING_PAGE, "gif_1", "ar", "/files/kept.gif")
		self.add_arabic(
			banners=[("/files/ar-hero-1.jpg", "/ar-1"), ("", "/ar-2"), ("/files/ar-hero-3.jpg", "")]
		)

		migration.execute()

		self.assertEqual(
			self.translations(LANDING_PAGE, LANDING_PAGE)["gif_1"].translated_value, "/files/kept.gif"
		)
		# The second Arabic banner has no image, so English banner 2 keeps its own.
		self.assertEqual(
			{
				field: row.translated_value
				for field, row in self.translations(BANNER, self.english_banners[1]).items()
			},
			{"url": "/ar-2"},
		)
		archived = [
			(row["field"], row["hero_banner_position"], row["value"], row["reason"])
			for row in self.archived_rows()
		]
		self.assertEqual(
			archived,
			[
				("gif_1_ar", "", "/files/ar-gif-1.gif", "a translation was already saved"),
				(
					"hero_banner_ar.banner_image",
					"3",
					"/files/ar-hero-3.jpg",
					"no English hero banner at this position",
				),
			],
		)
		[log] = [frappe.get_doc("Error Log", name) for name in self.archive_logs()]
		self.assertIn("Content Translation: 2.", log.error)
		assert_fields_removed(self)

	def test_a_failed_archive_save_keeps_the_values(self):
		register(LANDING_PAGE, LANDING_PAGE, "gif_1", "ar", "/files/kept.gif")
		self.add_arabic(banners=[("/files/ar-hero-1.jpg", "/ar-1")])

		with (
			patch.object(File, "insert", side_effect=frappe.ValidationError("disk full")),
			self.assertRaises(frappe.ValidationError),
		):
			migration.execute()

		self.assertEqual(migration.read_singles(list(ARABIC)), ARABIC)
		self.assertEqual(len(migration.read_banners(migration.TABLE)), 1)

	def test_a_second_run_and_a_site_without_the_fields_change_nothing(self):
		self.add_arabic()
		migration.execute()
		register(LANDING_PAGE, LANDING_PAGE, "gif_1", "ar", "/files/new.gif")

		migration.execute()

		assert_fields_removed(self)
		rows = self.translations(LANDING_PAGE, LANDING_PAGE)
		self.assertEqual(rows["gif_1"].translated_value, "/files/new.gif")
		self.assertEqual(len(rows), len(ARABIC))
		self.assertEqual(self.archive_files(), [])


def keep_landing_page(test):
	"""Restore the Single and its banners at the very end: the patch commits."""
	singles = frappe.db.sql("select field, value from tabSingles where doctype=%s", LANDING_PAGE)
	banners = frappe.get_all(BANNER, filters={"parent": LANDING_PAGE}, fields=["*"])
	test.addCleanup(restore_landing_page, singles, banners)


def restore_landing_page(singles, banners):
	clear_landing_page()
	for field, value in singles:
		write_single(field, value)
	for row in banners:
		frappe.get_doc({**row, "doctype": BANNER}).db_insert()
	frappe.db.commit()  # nosemgrep: frappe-manual-commit
	frappe.clear_document_cache(LANDING_PAGE, LANDING_PAGE)


def clear_landing_page():
	fields = [*ENGLISH, *migration.FIELDS]
	frappe.db.delete("Singles", {"doctype": LANDING_PAGE, "field": ("in", fields)})
	frappe.db.delete(BANNER, {"parent": LANDING_PAGE})


def write_single(field, value):
	# Raw rows: the dropped fields are not on the doctype any more.
	singles = frappe.qb.DocType("Singles")
	frappe.qb.from_(singles).delete().where(
		(singles.doctype == LANDING_PAGE) & (singles.field == field)
	).run()
	frappe.qb.into(singles).columns("doctype", "field", "value").insert(LANDING_PAGE, field, value).run()


def add_banner(table, index, image, url):
	row = frappe.get_doc(
		{
			"doctype": BANNER,
			"parent": LANDING_PAGE,
			"parenttype": LANDING_PAGE,
			"parentfield": table,
			"idx": index,
			"banner_image": image,
			"url": url,
		}
	)
	row.db_insert()
	return row.name


def assert_fields_removed(test):
	test.assertEqual(migration.read_singles(list(migration.FIELDS)), {})
	test.assertEqual(migration.read_banners(migration.TABLE), [])
