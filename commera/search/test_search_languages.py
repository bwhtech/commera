# Copyright (c) 2026, hussain@buildwithhussain.com and Contributors
# See license.txt

import copy
import os
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import CallbackManager
from rq.job import JobStatus

from commera import utils
from commera.localization import content as localization_content
from commera.localization import register
from commera.search import query as search_query
from commera.search import record_builder, sync
from commera.search.catalogue_fixtures import SEARCH_TOKEN, STYLE_ITEM, SearchCatalogue
from commera.search.engine_cache import clear_search_engine
from commera.search.sqlite_product_search import SqliteProductSearch
from commera.search.translations import search_languages_changed
from commera.tests.test_localization import set_storefront_languages
from commera.utils import translated_title_matches

TEST_INDEX_NAME = "test_commera_search_languages.db"
PRODUCT = "Style Attribute Variant"
CATEGORY = "Ecommerce Category"
SETTINGS_MODULE = "commera.commera_ecommerce.doctype.commera_settings.commera_settings"

FRENCH_TITLE, FRENCH_TERM = "Zzbidule Rouge Premium", "zzbidule"
ARABIC_TITLE, ARABIC_TERM = "ودجت أحمر فاخر", "ودجت"
FRENCH_CATEGORY, FRENCH_CATEGORY_TERM = "Zzrayon Bidules", "zzrayon"
ARABIC_CATEGORY, ARABIC_CATEGORY_TERM = "منوعات الأحذية الرياضية", "منوعات"


class TestSearchLanguages(SearchCatalogue, IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Each cleanup is registered before its change, so a failing setUpClass still undoes it.
		cls.swap_engine_attribute("INDEX_NAME", TEST_INDEX_NAME)
		cls.addClassCleanup(cls.drop_test_index)
		cls.addClassCleanup(cls.drop_fixtures)

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
	def swap_engine_attribute(cls, name, value):
		cls.addClassCleanup(setattr, SqliteProductSearch, name, getattr(SqliteProductSearch, name))
		setattr(SqliteProductSearch, name, value)

	@classmethod
	def drop_fixtures(cls):
		# Deleting the records also deletes their translations.
		cls.drop_catalogue()
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	@classmethod
	def drop_test_index(cls):
		SqliteProductSearch().drop_index()

	def setUp(self):
		self.publish("en", "fr", "ar")

	@classmethod
	def scope_index_to_fixtures(cls):
		scoped = copy.deepcopy(SqliteProductSearch.INDEXABLE_DOCTYPES)
		scoped[PRODUCT]["filters"] = {"is_published": 1, "name": ("in", [cls.red, cls.blue, cls.green])}
		scoped[CATEGORY]["filters"] = {"enabled": 1, "name": ("in", [cls.category])}
		cls.swap_engine_attribute("INDEXABLE_DOCTYPES", scoped)

	def publish(self, *codes):
		"""Publish `codes`, then rebuild the index as a publish does."""
		self.publish_languages(*codes)
		self.rebuild_index()

	def rebuild_index(self):
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

	def test_non_arabic_queries_keep_cores_match_expression(self):
		from frappe.search.sqlite_search import SQLiteSearch

		engine = SqliteProductSearch()
		for query in ("red shoes", 'say "hi" OR not', "a\x00b"):
			with self.subTest(query=query):
				expected = SQLiteSearch._prepare_fts_query(engine, query.replace("\x00", ""))
				self.assertEqual(engine._prepare_fts_query(query), expected)

	def test_arabic_queries_match_with_or_without_the_article(self):
		self.add_titles("ar", {self.blue: "القميص الأزرق", self.green: "قميص أخضر للمدرسة"})
		for term in ("قميص", "القميص", "قَمِيص"):
			with self.subTest(term=term):
				self.assertEqual(set(self.product_names(term)), {self.blue, self.green})
				self.assertEqual(set(self.engine.search_products({"search": term})), {self.blue, self.green})
		self.assertEqual(self.product_names("ازرق"), [self.blue])

	def test_arabic_queries_fold_alef_and_ta_marbuta(self):
		self.add_titles("ar", {self.green: "قميص أخضر للمدرسة"})
		for term in ("مدرسه", "المدرسة", "مدرسة"):
			with self.subTest(term=term):
				self.assertEqual(self.product_names(term), [self.green])
		# The red title has "أحمر": a query with a bare alef or with the article still finds it.
		for term in ("احمر", "الأحمر", "إحمر"):
			with self.subTest(term=term):
				self.assertEqual(self.product_names(term), [self.red])

	def test_arabic_spellings_find_each_other(self):
		# Folding and article stripping must agree: "العاب" once lost "ألعاب" to its stem "عاب".
		self.add_titles("ar", {self.blue: "ألعاب مكتبة مستشفى", self.green: "العاب مكتبه مستشفي"})
		self.rebuild_index()
		for term in ("ألعاب", "العاب", "مكتبة", "مكتبه", "مستشفى", "مستشفي"):
			with self.subTest(term=term):
				self.assertEqual(set(self.product_names(term)), {self.blue, self.green})
				self.assertEqual(set(self.engine.search_products({"search": term})), {self.blue, self.green})
		for term in ("أحمر", "احمر"):
			with self.subTest(term=term):
				self.assertEqual(self.product_names(term), [self.red])

	def test_a_word_that_only_looks_like_it_has_an_article_matches_in_full(self):
		self.add_titles("ar", {self.blue: "هدية فالنتين"})
		self.rebuild_index()
		self.assertEqual(self.product_names("فالنتين"), [self.blue])
		self.assertEqual(self.engine.search_products({"search": "فالنتين"}), [self.blue])

	def test_a_partial_arabic_word_matches_as_a_prefix(self):
		self.add_titles("ar", {self.blue: "الوردة الحمراء"})
		self.rebuild_index()
		self.assertEqual(self.engine.search_products({"search": "الورد"}), [self.blue])
		typeahead = self.engine.typeahead("الورد")
		self.assertEqual(typeahead["product_names"], [self.blue])
		self.assertEqual(typeahead["corrected_words"], {})

	def test_arabic_category_names_match_normalised_forms(self):
		for term in ("أحذية", "احذيه", "الاحذية", "رياضيه"):
			with self.subTest(term=term):
				self.assertEqual(self.engine.typeahead(term)["category_names"], [self.category])

	def test_arabic_titles_keep_their_written_form(self):
		self.add_titles("ar", {self.blue: "القميص الأزرق"})
		[record] = record_builder.build_product_search_records([self.blue])
		self.assertEqual(record["titles"]["ar"], "القميص الأزرق")
		[row] = self.engine.sql(
			"SELECT content FROM search_fts WHERE doc_id = ?", (f"{PRODUCT}:{self.blue}",), read_only=True
		)
		self.assertIn("القميص الأزرق", row["content"])
		# Each word is held folded, and without its article when one is present.
		self.assertLessEqual({"قميص", "الازرق", "ازرق"}, set(row["content"].split()))

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

	def test_the_like_fallback_skips_unpublished_languages(self):
		with patch("commera.search.sync.frappe.enqueue"):
			name = register(PRODUCT, self.blue, "display_name", "de", "Zzding Blau")
		self.addCleanup(frappe.db.delete, "Content Translation", name)
		frappe.set_user("Guest")
		self.addCleanup(frappe.set_user, "Administrator")
		self.assertTrue(search_query.use_qb_fallback({"search": "Zzd"}))
		self.assertNotIn(self.blue, [card["name"] for card in utils.get_product_list({"search": "Zzd"})])
		self.assertEqual(translated_title_matches("Zzding").run(pluck=True), [])

	def test_the_like_fallback_needs_a_search_language(self):
		self.publish("en")
		self.assertIsNone(translated_title_matches("Zzbid"))
		self.assertNotIn(self.red, [card["name"] for card in utils.get_product_list({"search": "Zzb"})])

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

	def test_moving_a_translation_to_an_unpublished_language_drops_its_title(self):
		name = self.add_titles("fr", {self.blue: "Zzmachin Bleu"})[0]
		self.assertEqual(self.product_names("zzmachin"), [self.blue])
		upserted = self.edit_translation(name, language="de")
		self.assertEqual(upserted, [(PRODUCT, self.blue)])
		self.assertEqual(self.product_names("zzmachin"), [])

	def test_moving_a_translation_to_another_product_reindexes_both(self):
		name = self.add_titles("fr", {self.blue: "Zzmachin Bleu"})[0]
		upserted = self.edit_translation(name, reference_name=self.green)
		self.assertEqual(set(upserted), {(PRODUCT, self.blue), (PRODUCT, self.green)})
		self.assertEqual(self.product_names("zzmachin"), [self.green])

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

	def test_a_language_change_during_a_build_rebuilds_again(self):
		def change_languages(*args, **kwargs):
			if not changed:
				changed.append(True)
				set_storefront_languages("en", published=("en", "fr"))
			return paginate(*args, **kwargs)

		changed, paginate = [], SqliteProductSearch.get_documents_paginated
		with patch.object(SqliteProductSearch, "get_documents_paginated", autospec=True) as patched:
			patched.side_effect = change_languages
			callbacks = self.build_with_after_commit()
		# Started builds suppress a deduplicated enqueue, so the build must enqueue its own successor.
		with patch.object(SqliteProductSearch, "enqueue_full_rebuild") as rebuild:
			callbacks.run()
		rebuild.assert_called_once_with()

	def test_a_build_with_unchanged_languages_or_a_queued_build_enqueues_nothing(self):
		callbacks = self.build_with_after_commit()
		with patch.object(SqliteProductSearch, "enqueue_full_rebuild") as rebuild:
			callbacks.run()
		rebuild.assert_not_called()

		callbacks = self.build_with_after_commit()
		set_storefront_languages("en", published=("en",))
		with (
			patch.object(SqliteProductSearch, "enqueue_full_rebuild") as rebuild,
			patch("commera.search.translations.get_job_status", return_value=JobStatus.QUEUED),
		):
			callbacks.run()
		rebuild.assert_not_called()

	def test_resuming_a_build_after_a_language_change_starts_again(self):
		self.interrupt_build()
		set_storefront_languages("en", published=("en", "fr"))
		self.resume_build()
		content = self.indexed_content(self.red)
		self.assertIn(FRENCH_TITLE, content)
		self.assertNotIn(ARABIC_TITLE, content)
		codes = {row["code"] for row in self.engine.sql("SELECT code FROM search_language", read_only=True)}
		self.assertEqual(codes, {"en", "fr"})

	def test_resuming_a_build_with_the_same_languages_continues_it(self):
		self.interrupt_build()
		fetched, paginate = [], SqliteProductSearch.get_documents_paginated

		def record_doctype(*args, **kwargs):
			fetched.append(args[1])
			return paginate(*args, **kwargs)

		with patch.object(SqliteProductSearch, "get_documents_paginated", autospec=True) as patched:
			patched.side_effect = record_doctype
			self.resume_build()
		self.assertNotIn(PRODUCT, fetched)
		self.assertIn(ARABIC_TITLE, self.indexed_content(self.red))
		self.assertEqual(self.engine.typeahead(FRENCH_CATEGORY_TERM)["category_names"], [self.category])

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

	def add_titles(self, language, titles):
		"""Register `titles` {product: title} in `language` and index them, removed after the test."""
		with patch("commera.search.sync.frappe.enqueue"):
			names = [
				register(PRODUCT, product, "display_name", language, title)
				for product, title in titles.items()
			]
		# setUp rebuilds the index for the next test, so only the rows need removing.
		self.addCleanup(frappe.db.delete, "Content Translation", {"name": ("in", names)})
		SqliteProductSearch().index_docs(PRODUCT, list(titles))
		return names

	def edit_translation(self, name, **changes):
		"""Save `changes` to a translation, then run the upserts it enqueued. Returns them."""
		translation = frappe.get_doc("Content Translation", name)
		with patch("commera.search.sync.frappe.enqueue") as enqueue:
			translation.update(changes).save(ignore_permissions=True)
		for doctype, record in upserts(enqueue):
			sync.upsert_doc(doctype, record)
		return upserts(enqueue)

	def build_with_after_commit(self):
		"""Rebuild the index. Returns the after-commit callbacks the build left, without running them."""
		callbacks = CallbackManager()
		with patch.object(frappe.db, "after_commit", callbacks):
			SqliteProductSearch().drop_index()
			SqliteProductSearch().build_index()
		return callbacks

	def interrupt_build(self):
		"""Start a fresh build that dies after the products. Its temporary database stays."""
		temp_path = SqliteProductSearch()._get_db_path(is_temp=True)
		self.addCleanup(lambda: os.path.exists(temp_path) and os.unlink(temp_path))
		paginate = SqliteProductSearch.get_documents_paginated

		def fail_on_categories(*args, **kwargs):
			if args[1] == CATEGORY:
				raise RuntimeError("interrupted")
			return paginate(*args, **kwargs)

		SqliteProductSearch().drop_index()
		with (
			patch.object(SqliteProductSearch, "get_documents_paginated", autospec=True) as patched,
			patch.object(frappe.db, "after_commit", CallbackManager()),
			patch("frappe.search.sqlite_search.frappe.log_error"),
			self.assertRaises(RuntimeError),
		):
			patched.side_effect = fail_on_categories
			SqliteProductSearch().build_index()
		self.assertTrue(os.path.exists(temp_path))

	def resume_build(self):
		with patch.object(frappe.db, "after_commit", CallbackManager()):
			SqliteProductSearch().build_index(is_continuation=True)
		self.engine = SqliteProductSearch()

	def indexed_content(self, product):
		[row] = self.engine.sql(
			"SELECT content FROM search_fts WHERE doc_id = ?", (f"{PRODUCT}:{product}",), read_only=True
		)
		return row["content"]

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
