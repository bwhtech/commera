"""The patch that moves the Landing Page Settings Arabic fields into Content Translation."""

from unittest.mock import patch

import frappe
from frappe.core.doctype.file.file import File
from frappe.utils import cstr
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
HOSTILE_IMAGE = '/files/a" onerror="alert(1)'
ENGLISH_BANNERS = [("/files/en-hero-1.jpg", "/en-1"), ("/files/en-hero-2.jpg", "/en-2")]


class TestMoveLandingPageArabicFields(ArabicArchiveTestCase):
	migration = migration

	def setUp(self):
		super().setUp()
		keep_landing_page(self)
		keep_request(self)
		self.addCleanup(self.delete_translations)
		clear_landing_page()
		for field, value in ENGLISH.items():
			write_single(field, value)
		for index, (image, url) in enumerate(ENGLISH_BANNERS, start=1):
			add_banner("hero_banner", index, image, url)

	def delete_translations(self):
		frappe.db.delete(
			"Content Translation",
			{"reference_doctype": LANDING_PAGE, "creation": (">=", self.started)},
		)
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	def add_arabic(self, banners=(), values=ARABIC):
		for field, value in values.items():
			write_single(field, value)
		for index, (image, url) in enumerate(banners, start=1):
			add_banner(migration.TABLE, index, image, url)

	def homepage(self, lang):
		frappe.local.request = Request(EnvironBuilder(path=f"/{lang}/").get_environ())
		frappe.local.request_cache.clear()
		frappe.clear_document_cache(LANDING_PAGE, LANDING_PAGE)
		return homepage.get_homepage_details()

	def hero_banners(self, lang):
		return [(cstr(row.banner_image), row.url) for row in self.homepage(lang).hero_banner]

	def test_values_are_copied_and_the_homepage_shows_them_in_arabic(self):
		self.add_arabic()

		migration.execute()

		rows = self.translations(LANDING_PAGE, LANDING_PAGE)
		self.assertEqual(
			{field: row.translated_value for field, row in rows.items()},
			{"gif_1": "/files/ar-gif-1.gif", "gif_url_1": "/collections/ar", "banner_url_1": "/ar-sale"},
		)
		self.assertEqual(rows["gif_1"].source_hash, get_source_hash(ENGLISH["gif_1"]))
		source = frappe.db.get_single_value(LANDING_PAGE, "banner_url_1")
		self.assertEqual(rows["banner_url_1"].source_hash, get_source_hash(source))
		self.assertEqual(self.archive_files(), [])
		assert_fields_removed(self)

		arabic = self.homepage("ar")
		self.assertEqual(
			(arabic.gif_1, arabic.gif_url_1, arabic.banner_1, arabic.banner_url_1),
			("/files/ar-gif-1.gif", "/collections/ar", "/files/en-banner.jpg", "/ar-sale"),
		)
		english = self.homepage("en")
		self.assertEqual((english.gif_1, english.gif_url_1), (ENGLISH["gif_1"], ENGLISH["gif_url_1"]))

	def test_arabic_banners_replace_the_english_ones_on_arabic_pages_only(self):
		self.add_arabic(banners=[("/files/ar-hero-1.jpg", "/ar-1")])

		migration.execute()

		self.assertEqual(self.hero_banners("ar"), [("/files/ar-hero-1.jpg", "/ar-1")])
		self.assertEqual(self.hero_banners("en"), ENGLISH_BANNERS)
		rows = migration.read_banners(migration.SOURCE_TABLE)
		self.assertEqual([(row.idx, row.language) for row in rows], [(1, None), (2, None), (3, "ar")])

	def test_arabic_banners_without_english_ones_are_kept_in_order(self):
		frappe.db.delete(BANNER, {"parent": LANDING_PAGE})
		arabic = [("/files/ar-hero-1.jpg", "/ar-1"), ("/files/ar-hero-2.jpg", "/ar-2")]
		# Inserted in reverse: the order on the page is idx, not insertion.
		for index, (image, url) in reversed(list(enumerate(arabic, start=1))):
			add_banner(migration.TABLE, index, image, url)

		migration.execute()

		self.assertEqual(self.hero_banners("ar"), arabic)
		self.assertEqual(self.hero_banners("en"), [])
		self.assertEqual(self.archive_files(), [])

	def test_a_blank_arabic_banner_value_stays_blank(self):
		self.add_arabic(banners=[("", "/ar-1"), ("/files/ar-hero-2.jpg", "")])

		migration.execute()

		rows = migration.read_banners(migration.SOURCE_TABLE)[2:]
		self.assertEqual(
			[(cstr(row.banner_image), cstr(row.url)) for row in rows],
			[("", "/ar-1"), ("/files/ar-hero-2.jpg", "")],
		)
		# An empty link renders as the homepage, as the template always did.
		self.assertEqual(self.hero_banners("ar"), [("", "/ar-1"), ("/files/ar-hero-2.jpg", "/")])

	def test_default_links_padding_whitespace_and_kept_translations(self):
		register(LANDING_PAGE, LANDING_PAGE, "gif_1", "ar", "/files/kept.gif")
		write_single("gif_url_2", "/")
		write_single("gif_url_3", "/en-3")
		values = {
			**ARABIC,
			"gif_url_2_ar": "/",
			"gif_url_3_ar": "/",
			"gif_2_ar": "  /files/ar-gif-2.gif ",
			"gif_3_ar": " \t\n",
		}
		self.add_arabic(values=values)

		migration.execute()

		rows = self.translations(LANDING_PAGE, LANDING_PAGE)
		self.assertEqual(rows["gif_1"].translated_value, "/files/kept.gif")
		# "/" over an English "/" equals it verbatim, so skipping it loses nothing.
		self.assertNotIn("gif_url_2", rows)
		self.assertEqual(rows["gif_url_3"].translated_value, "/")
		self.assertEqual(rows["gif_2"].translated_value, "  /files/ar-gif-2.gif ")
		self.assertNotIn("gif_3", rows)
		archived = [(row["field"], row["value"], row["reason"]) for row in self.archived_rows()]
		self.assertEqual(
			sorted(archived),
			[
				("gif_1_ar", "/files/ar-gif-1.gif", "a translation was already saved"),
				("gif_3_ar", " \t\n", "whitespace only"),
			],
		)
		[log] = [frappe.get_doc("Error Log", name) for name in self.archive_logs()]
		self.assertIn("Content Translation: 2.", log.error)
		assert_fields_removed(self)

	def test_hostile_images_and_links_render_inert(self):
		# Arabic: three translations, one `_()` fallback of the English gif 2 and one tagged banner.
		hostile = {
			"gif_1_ar": HOSTILE_IMAGE,
			"gif_url_1_ar": "javascript:alert(1)",
			"banner_1_ar": HOSTILE_IMAGE,
		}
		self.add_arabic(values=hostile)
		write_single("gif_2", HOSTILE_IMAGE)
		write_single("gif_url_2", "javascript:alert(2)")
		add_banner("hero_banner", 3, HOSTILE_IMAGE, " JaVa\tScript:alert(3)", language="ar")

		migration.execute()

		for lang, images, links in (("ar", 4, 3), ("en", 1, 1)):
			with self.subTest(lang):
				html = render_homepage(self.homepage(lang))
				self.assertNotIn('" onerror="', html)
				self.assertNotIn("script:alert", html.lower())
				self.assertEqual(html.count('src="/files/a&#34; onerror=&#34;alert(1)"'), images)
				self.assertEqual(html.count('<a href="#" class="banner-effect">'), links)

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
		self.add_arabic(banners=[("/files/ar-hero-1.jpg", "/ar-1")])
		migration.execute()
		register(LANDING_PAGE, LANDING_PAGE, "gif_1", "ar", "/files/new.gif")

		migration.execute()

		assert_fields_removed(self)
		rows = self.translations(LANDING_PAGE, LANDING_PAGE)
		self.assertEqual(rows["gif_1"].translated_value, "/files/new.gif")
		self.assertEqual(len(rows), len(ARABIC))
		self.assertEqual(len(migration.read_banners(migration.SOURCE_TABLE)), 3)
		self.assertEqual(self.archive_files(), [])


def render_homepage(details):
	template = (
		'{% import "templates/macros/carousel.html" as carousel %}'
		'{% import "templates/macros/item_carousel.html" as item_carousel %}'
		'{% include "templates/partials/index/uncontained_body.html" %}'
	)
	return frappe.render_template(
		template, {"homepage_details": details, "new_arrivals": [], "best_picks": []}
	)


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
	fields = [*migration.TRANSLATED, *migration.FIELDS]
	frappe.db.delete("Singles", {"doctype": LANDING_PAGE, "field": ("in", fields)})
	frappe.db.delete(BANNER, {"parent": LANDING_PAGE})


def write_single(field, value):
	# Raw rows: the dropped fields are not on the doctype any more.
	singles = frappe.qb.DocType("Singles")
	frappe.qb.from_(singles).delete().where(
		(singles.doctype == LANDING_PAGE) & (singles.field == field)
	).run()
	frappe.qb.into(singles).columns("doctype", "field", "value").insert(LANDING_PAGE, field, value).run()


def add_banner(table, index, image, url, language=None):
	row = frappe.get_doc(
		{
			"doctype": BANNER,
			"parent": LANDING_PAGE,
			"parenttype": LANDING_PAGE,
			"parentfield": table,
			"idx": index,
			"banner_image": image,
			"url": url,
			"language": language,
		}
	)
	row.db_insert()
	return row.name


def assert_fields_removed(test):
	test.assertEqual(migration.read_singles(list(migration.FIELDS)), {})
	test.assertEqual(migration.read_banners(migration.TABLE), [])
