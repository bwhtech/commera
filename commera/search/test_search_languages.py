# Copyright (c) 2026, hussain@buildwithhussain.com and Contributors
# See license.txt

import copy
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commera import utils
from commera.localization import content as localization_content
from commera.localization import register
from commera.search import query as search_query
from commera.search import record_builder, sync
from commera.search.catalogue_fixtures import SEARCH_TOKEN, STYLE_ITEM, SearchCatalogue
from commera.search.engine_cache import clear_search_engine
from commera.search.sqlite_product_search import SqliteProductSearch
from commera.search.translations import search_languages_changed
from commera.utils import translated_title_matches

TEST_INDEX_NAME = "test_commera_search_languages.db"
PRODUCT = "Style Attribute Variant"
CATEGORY = "Ecommerce Category"
SETTINGS_MODULE = "commera.commera_ecommerce.doctype.commera_settings.commera_settings"

FRENCH_TITLE, FRENCH_TERM = "Zzbidule Rouge Premium", "zzbidule"
ARABIC_TITLE, ARABIC_TERM = "ودجت أحمر فاخر", "ودجت"
FRENCH_CATEGORY, FRENCH_CATEGORY_TERM = "Zzrayon Bidules", "zzrayon"
ARABIC_CATEGORY, ARABIC_CATEGORY_TERM = "منوعات تجريبية", "منوعات"


class TestSearchLanguages(SearchCatalogue, IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.original_index_name = SqliteProductSearch.INDEX_NAME
		cls.original_indexable = SqliteProductSearch.INDEXABLE_DOCTYPES
		SqliteProductSearch.INDEX_NAME = TEST_INDEX_NAME

		settings = frappe.get_cached_doc("Commera Settings")
		cls.default_price_list = settings.default_price_list
		cls.sale_price_list = settings.sale_price_list
		cls.price_names = {}

		cls.drop_catalogue()
		cls.build_catalogue()
		cls.scope_index_to_fixtures()
		with patch("commera.search.sync.frappe.enqueue"):
			for doctype, name, language, value in (
				(PRODUCT, cls.red, "fr", FRENCH_TITLE),
				(PRODUCT, cls.red, "ar", ARABIC_TITLE),
				(CATEGORY, cls.category, "fr", FRENCH_CATEGORY),
				(CATEGORY, cls.category, "ar", ARABIC_CATEGORY),
			):
				register(doctype, name, "display_name", language, value)
		# Fixtures outlive one test method, so they are committed and torn down explicitly.
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	@classmethod
	def tearDownClass(cls):
		# Deleting the records also deletes their translations.
		cls.drop_catalogue()
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		SqliteProductSearch().drop_index()
		SqliteProductSearch.INDEX_NAME = cls.original_index_name
		SqliteProductSearch.INDEXABLE_DOCTYPES = cls.original_indexable
		super().tearDownClass()

	def setUp(self):
		self.publish("en", "fr", "ar")

	@classmethod
	def scope_index_to_fixtures(cls):
		scoped = copy.deepcopy(SqliteProductSearch.INDEXABLE_DOCTYPES)
		scoped[PRODUCT]["filters"] = {"is_published": 1, "name": ("in", [cls.red, cls.blue, cls.green])}
		scoped[CATEGORY]["filters"] = {"enabled": 1, "name": ("in", [cls.category])}
		SqliteProductSearch.INDEXABLE_DOCTYPES = scoped

	def publish(self, *codes):
		"""Publish `codes`, then rebuild the index as a publish does."""
		self.publish_languages(*codes)
		clear_search_engine()
		SqliteProductSearch().drop_index()
		SqliteProductSearch().build_index()
		# A fresh engine: the building one memoized its readiness before the new index was swapped in.
		self.engine = SqliteProductSearch()

	def product_names(self, term):
		return self.engine.typeahead(term)["product_names"]

	# -- queries -----------------------------------------------------------------------------------

	def test_a_french_query_matches_the_french_title(self):
		self.assertFalse(search_query.use_qb_fallback({"search": FRENCH_TERM}))
		self.assertEqual(self.product_names(FRENCH_TERM), [self.red])
		self.assertEqual(self.engine.search_products({"search": FRENCH_TERM}), [self.red])
		self.assertEqual(self.engine.search_count({"search": FRENCH_TERM}), 1)

	def test_an_arabic_query_matches_the_arabic_title_through_the_index(self):
		self.assertTrue(self.engine.can_rank(ARABIC_TERM))
		self.assertFalse(search_query.use_qb_fallback({"search": ARABIC_TERM}))
		self.assertEqual(self.product_names(ARABIC_TERM), [self.red])
		self.assertEqual(
			[card["name"] for card in utils.get_product_list({"search": ARABIC_TERM})], [self.red]
		)

	def test_translated_category_names_are_indexed(self):
		self.assertEqual(self.engine.typeahead(FRENCH_CATEGORY_TERM)["category_names"], [self.category])
		self.assertEqual(self.engine.typeahead(ARABIC_CATEGORY_TERM)["category_names"], [self.category])

	def test_english_queries_still_match(self):
		self.assertEqual(set(self.product_names(SEARCH_TOKEN)), {self.red, self.blue, self.green})

	# -- what the index holds ----------------------------------------------------------------------

	def test_only_published_languages_are_indexed(self):
		self.publish("en", "fr")
		[record] = record_builder.build_product_search_records([self.red])
		self.assertEqual(record["titles"], {"fr": FRENCH_TITLE})
		self.assertNotIn(ARABIC_TITLE, record["content"])
		# Without Arabic in the index, an Arabic term goes to frappe.qb.
		self.assertFalse(self.engine.can_rank(ARABIC_TERM))

	def test_an_index_without_its_language_table_counts_as_missing(self):
		# An index built before this change has no language table, so the next migrate rebuilds it.
		self.engine.sql("DROP TABLE search_language", commit=True)
		self.assertFalse(SqliteProductSearch().index_exists())

	def test_the_legacy_arabic_name_fills_a_missing_translation(self):
		if not self.has_legacy_field():
			self.skipTest("Item has no custom_item_name_ar field on this site")
		frappe.db.set_value("Item", STYLE_ITEM, "custom_item_name_ar", "قديم تجريبي")
		self.addCleanup(frappe.db.set_value, "Item", STYLE_ITEM, "custom_item_name_ar", None)
		records = record_builder.build_product_search_records([self.red, self.blue])
		titles = {record["name"]: record["titles"]["ar"] for record in records}
		self.assertEqual(titles, {self.red: ARABIC_TITLE, self.blue: "قديم تجريبي"})

	def test_a_rebuild_reads_translations_once_per_language(self):
		with patch.object(
			localization_content, "fetch_translations", wraps=localization_content.fetch_translations
		) as fetch:
			record_builder.build_product_search_records([self.red, self.blue, self.green])
		self.assertEqual(fetch.call_count, 2)

	def test_short_terms_match_translated_titles_on_frappe_qb(self):
		# Too short for SQLite, so frappe.qb serves it and must look in the translations too.
		self.assertTrue(search_query.use_qb_fallback({"search": "ودج"}))
		self.assertEqual([card["name"] for card in utils.get_product_list({"search": "ودج"})], [self.red])
		self.assertEqual(translated_title_matches("Zzbid").run(pluck=True), [self.red])

	# -- keeping the index fresh ---------------------------------------------------------------------

	def test_saving_a_translation_reindexes_its_record(self):
		with patch("commera.search.sync.frappe.enqueue") as enqueue:
			name = register(PRODUCT, self.blue, "display_name", "fr", "Zzmachin Bleu")
		self.addCleanup(self.delete_translation, name, self.blue)
		self.assertEqual(upserts(enqueue), [(PRODUCT, self.blue)])

		sync.upsert_doc(PRODUCT, self.blue)
		self.assertEqual(self.product_names("zzmachin"), [self.blue])

		with patch("commera.search.sync.frappe.enqueue") as enqueue:
			frappe.delete_doc("Content Translation", name, ignore_permissions=True)
		self.assertEqual(upserts(enqueue), [(PRODUCT, self.blue)])
		sync.upsert_doc(PRODUCT, self.blue)
		self.assertEqual(self.product_names("zzmachin"), [])

	def test_other_translations_leave_the_index_alone(self):
		with patch("commera.search.sync.frappe.enqueue") as enqueue:
			names = [
				register(PRODUCT, self.blue, "meta_title", "fr", "Zzmachin"),
				register(PRODUCT, self.blue, "display_name", "de", "Zzding Blau"),
			]
		for name in names:
			self.addCleanup(frappe.db.delete, "Content Translation", name)
		self.assertEqual(upserts(enqueue), [])

	def test_publishing_a_language_rebuilds_the_index(self):
		before = frappe.get_single("Commera Settings")
		settings = frappe.get_single("Commera Settings")
		settings.append("storefront_languages", {"language": "de", "published": 1})
		settings._doc_before_save = before
		with (
			patch(f"{SETTINGS_MODULE}.enqueue_full_rebuild") as rebuild,
			patch(f"{SETTINGS_MODULE}.clear_website_cache"),
			patch("commera.migrate.setup_robots_txt"),
		):
			settings.on_update()
		rebuild.assert_called_once_with(deduplicate=True)

	def test_only_index_languages_count_as_a_change(self):
		before = frappe.get_single("Commera Settings")
		unpublished = frappe.get_single("Commera Settings")
		unpublished.append("storefront_languages", {"language": "de", "published": 0})
		self.assertFalse(search_languages_changed(before, unpublished))
		published = frappe.get_single("Commera Settings")
		published.storefront_languages = [
			row for row in published.storefront_languages if row.language != "fr"
		]
		self.assertTrue(search_languages_changed(before, published))

	# -- helpers -----------------------------------------------------------------------------------

	def delete_translation(self, name, record):
		frappe.db.delete("Content Translation", name)
		sync.upsert_doc(PRODUCT, record)

	def has_legacy_field(self):
		return frappe.db.has_column("Item", "custom_item_name_ar")


def upserts(enqueue):
	"""The (doctype, name) of each index upsert a patched frappe.enqueue received."""
	return [
		(call.kwargs["doctype"], call.kwargs["name"])
		for call in enqueue.call_args_list
		if call.args == ("commera.search.sync.upsert_doc",)
	]
