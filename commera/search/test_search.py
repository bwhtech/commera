# Copyright (c) 2026, hussain@buildwithhussain.com and Contributors
# See license.txt

import copy
import os
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from commera import utils
from commera.search import build, record_builder, sync
from commera.search import query as search_query
from commera.search.catalogue_fixtures import (
	ARABIC_TERM,
	BRAND,
	ITEM_ATTRIBUTE,
	ITEM_GROUP,
	ITEM_GROUP_BLUE,
	NON_PRIVILEGED_USER,
	SEARCH_TOKEN,
	SHORT_TERM,
	STYLE_ITEM,
	SearchCatalogue,
)
from commera.search.engine_cache import clear_search_engine
from commera.search.sqlite_product_search import SEARCH_CLASS_PATH, SqliteProductSearch
from commera.search.typeahead import get_typeahead

TEST_INDEX_NAME = "test_commera_product_search.db"


class TestStorefrontSearch(SearchCatalogue, IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.original_index_name = SqliteProductSearch.INDEX_NAME
		cls.original_indexable = SqliteProductSearch.INDEXABLE_DOCTYPES
		SqliteProductSearch.INDEX_NAME = TEST_INDEX_NAME
		SqliteProductSearch().drop_index()

		settings = frappe.get_cached_doc("Commera Settings")
		cls.default_price_list = settings.default_price_list
		cls.sale_price_list = settings.sale_price_list
		cls.price_names = {}

		cls.drop_catalogue()
		cls.build_catalogue()
		cls.scope_index_to_fixtures()
		cls.ensure_non_privileged_user()
		# Fixtures outlive one test method, so they are committed and torn down explicitly.
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	@classmethod
	def tearDownClass(cls):
		cls.drop_catalogue()
		# The committed fixtures survive the rollback, so the teardown has to be committed too.
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		SqliteProductSearch().drop_index()
		SqliteProductSearch.INDEX_NAME = cls.original_index_name
		SqliteProductSearch.INDEXABLE_DOCTYPES = cls.original_indexable
		super().tearDownClass()

	def setUp(self):
		# frappe.local persists across test methods, so a memoized index_exists() would leak between them.
		clear_search_engine()
		self.rebuild_index()

	# -- fixtures --------------------------------------------------------------------------------

	@classmethod
	def scope_index_to_fixtures(cls):
		scoped = copy.deepcopy(SqliteProductSearch.INDEXABLE_DOCTYPES)
		scoped["Style Attribute Variant"]["filters"] = {
			"is_published": 1,
			"name": ("in", [cls.red, cls.blue]),
		}
		scoped["Ecommerce Category"]["filters"] = {"enabled": 1, "name": ("in", [cls.category])}
		SqliteProductSearch.INDEXABLE_DOCTYPES = scoped

	def rebuild_index(self):
		engine = SqliteProductSearch()
		engine.drop_index()
		engine.build_index()

	# -- search vs frappe.qb dispatch ------------------------------------------------------------

	def test_latin_search_uses_sqlite(self):
		self.assertTrue(search_query.relevance_sort_available({"search": SEARCH_TOKEN}))
		self.assertFalse(search_query.use_qb_fallback({"search": SEARCH_TOKEN}))

		names = SqliteProductSearch().typeahead(SEARCH_TOKEN)["product_names"]
		self.assertIn(self.red, names)
		self.assertIn(self.blue, names)
		# green is published but not indexed, so the FTS path never surfaces it.
		self.assertNotIn(self.green, names)

		cards = get_typeahead(SEARCH_TOKEN)["products"]
		self.assertEqual({card["name"] for card in cards}, {self.red, self.blue})

	def test_arabic_search_falls_back_to_qb(self):
		self.assertTrue(search_query.use_qb_fallback({"search": ARABIC_TERM}))

	def test_short_term_falls_back_to_qb(self):
		self.assertTrue(search_query.use_qb_fallback({"search": SHORT_TERM}))

	def test_browse_without_term_stays_on_qb(self):
		self.assertTrue(search_query.use_qb_fallback({}))
		self.assertIsNone(search_query.listing_facets({}))

	def test_edit_distance_fallback_corrects_short_typo(self):
		# Trigram Jaccard alone leaves "zzwidgt" uncorrected; the Levenshtein fallback catches it.
		result = SqliteProductSearch().typeahead("zzwidgt")
		self.assertEqual(result["corrected_words"].get("zzwidgt"), SEARCH_TOKEN)
		self.assertEqual(set(result["product_names"]), {self.red, self.blue})

	# -- typeahead -------------------------------------------------------------------------------

	def test_typeahead_api_returns_cards_and_menu_links(self):
		from commera.api.search import typeahead

		frappe.local.commera_storefront_menu = None
		result = typeahead(SEARCH_TOKEN)
		self.assertEqual(result["query"], SEARCH_TOKEN)
		self.assertEqual({card["name"] for card in result["products"]}, {self.red, self.blue})
		self.assertIn("effective_price", result["products"][0])
		[category] = result["categories"]
		self.assertEqual(category["name"], self.category)
		self.assertTrue(category["url"].endswith("?category=zz_test_category"))
		self.assertIsNone(result["corrected_query"])

	def test_typeahead_offers_did_you_mean(self):
		self.assertEqual(get_typeahead("zzwidgt premium")["corrected_query"], f"{SEARCH_TOKEN} premium")

	def test_typeahead_lists_short_terms_from_qb(self):
		# SQLite cannot rank "zzw", so frappe.qb lists every published match, green included.
		result = get_typeahead("zzw", limit=10)
		self.assertEqual({card["name"] for card in result["products"]}, {self.red, self.blue, self.green})
		self.assertEqual(result["categories"], [])

	def test_typeahead_api_clamps_a_negative_limit(self):
		from commera.api.search import typeahead

		self.assertEqual(len(typeahead("zzw", limit=-1)["products"]), 1)

	def test_typeahead_finds_arabic_item_names(self):
		if not frappe.db.has_column("Item", "custom_item_name_ar"):
			self.skipTest("Item has no custom_item_name_ar field on this site")
		frappe.db.set_value("Item", STYLE_ITEM, "custom_item_name_ar", "ودجت تجريبي")
		self.addCleanup(frappe.db.set_value, "Item", STYLE_ITEM, "custom_item_name_ar", None)
		names = {card["name"] for card in get_typeahead("ودجت", limit=10)["products"]}
		self.assertEqual(names, {self.red, self.blue, self.green})

	def test_typeahead_counts_no_facets(self):
		# A plain function, not a MagicMock: core's scoring pipeline would take a mock for a scoring function.
		calls = []

		def spy(*args, **kwargs):
			calls.append(args)

		with patch.object(SqliteProductSearch, "count_facets", spy):
			get_typeahead(SEARCH_TOKEN)
		self.assertEqual(calls, [])

	def test_get_search_results_keeps_its_card_list(self):
		from commera.api.utils import get_search_results

		self.assertEqual({card["name"] for card in get_search_results(SEARCH_TOKEN)}, {self.red, self.blue})

	# -- facets ----------------------------------------------------------------------------------

	def test_facets_reflect_indexed_catalogue(self):
		facets = SqliteProductSearch().facet_counts({"search": SEARCH_TOKEN})
		self.assertEqual(facets["brand"].get(BRAND), 2)
		self.assertEqual(set(facets["category"]), {ITEM_GROUP, ITEM_GROUP_BLUE})
		self.assertEqual(facets["color"], {"Zzred": 1, "Zzblue": 1})
		self.assertEqual(facets["size"], {"8": 1, "10": 1, "38": 1, "40": 1})

		sidebar = search_query.listing_facets({"search": SEARCH_TOKEN})
		self.assertIn(BRAND, sidebar["brands"])
		self.assertEqual(set(sidebar["colors"]), {"Zzred", "Zzblue"})

	def test_listing_facet_counts_come_from_the_engine(self):
		counts = search_query.listing_facet_counts({"search": SEARCH_TOKEN, "sizes": ["8"]})

		self.assertEqual(counts["colors"], {"Zzred": 1})
		self.assertEqual(counts["sizes"], {"8": 1, "10": 1, "38": 1, "40": 1})

	def test_size_facet_is_ordered_numerically(self):
		# By count the order is arbitrary; as text 10 sorts before 8. Both are wrong for a numeric size scale.
		facets = SqliteProductSearch().facet_counts({"search": SEARCH_TOKEN})
		self.assertEqual(list(facets["size"]), ["8", "10", "38", "40"])

	def test_facets_narrow_by_the_other_selected_filters(self):
		engine = SqliteProductSearch()

		# Only red carries size 8, so every other facet collapses to red's values...
		narrowed = engine.facet_counts({"search": SEARCH_TOKEN, "sizes": ["8"]})
		self.assertEqual(set(narrowed["category"]), {ITEM_GROUP})
		self.assertEqual(narrowed["brand"], {BRAND: 1})
		# ...but the size facet must not narrow by itself, or the shopper could never widen the selection.
		self.assertEqual(list(narrowed["size"]), ["8", "10", "38", "40"])

		# Symmetrically: picking blue's category leaves only blue's sizes, and every category listed.
		by_category = engine.facet_counts({"search": SEARCH_TOKEN, "subcategory": [ITEM_GROUP_BLUE]})
		self.assertEqual(list(by_category["size"]), ["38", "40"])
		self.assertEqual(set(by_category["category"]), {ITEM_GROUP, ITEM_GROUP_BLUE})

	def test_sidebar_facets_agree_with_the_narrowed_grid(self):
		# The sidebar must not offer a size that the grid it sits next to cannot show.
		filters = {"search": SEARCH_TOKEN, "subcategory": [ITEM_GROUP_BLUE]}
		self.assertEqual(SqliteProductSearch().search_products(filters), [self.blue])
		self.assertEqual(search_query.listing_facets(filters)["sizes"], ["38", "40"])

	# -- ?category= tab scope --------------------------------------------------------------------

	def test_category_scope_narrows_both_grids(self):
		# ?category= used to retitle the page and leave the whole catalogue in the grid on both paths.
		filters = {"search": SEARCH_TOKEN, "category_item_groups": [ITEM_GROUP_BLUE]}
		engine = SqliteProductSearch()
		self.assertEqual(engine.search_products(filters), [self.blue])
		self.assertEqual(engine.search_count(filters), 1)
		self.assertEqual([card["name"] for card in utils.get_product_list_qb(filters)], [self.blue])
		self.assertEqual(utils.get_product_count_qb(filters), 1)

	def test_category_scope_holds_in_every_facet(self):
		# Each facet drops its own filter; the tab scope is no facet, so dropping it would offer dead options.
		facets = SqliteProductSearch().facet_counts(
			{
				"search": SEARCH_TOKEN,
				"category_item_groups": [ITEM_GROUP_BLUE],
				"subcategory": [ITEM_GROUP_BLUE],
			}
		)
		self.assertEqual(set(facets["category"]), {ITEM_GROUP_BLUE})
		self.assertEqual(list(facets["size"]), ["38", "40"])

	def test_listing_tab_narrows_to_its_item_groups(self):
		from commera.www.products import list as product_list_page

		self.link_category_to(ITEM_GROUP_BLUE)
		tab = frappe.db.get_value("Ecommerce Category", self.category, "route_slug")
		filters = {"search": SEARCH_TOKEN, "category": tab}
		self.assertIsNotNone(product_list_page.apply_category_scope(filters))
		self.assertEqual(filters["category_item_groups"], [ITEM_GROUP_BLUE])
		self.assertEqual([card["name"] for card in utils.get_product_list(filters)], [self.blue])

		# Browsing the tab without a term goes through frappe.qb, which must narrow the same way.
		browse = {"search": "", "category": tab}
		product_list_page.apply_category_scope(browse)
		self.assertEqual([card["name"] for card in utils.get_product_list(browse)], [self.blue])

	def test_unknown_listing_tab_is_dropped(self):
		from commera.www.products import list as product_list_page

		filters = {"search": SEARCH_TOKEN, "category": "no-such-tab"}
		self.assertIsNone(product_list_page.apply_category_scope(filters))
		self.assertEqual(filters["category"], "")
		self.assertNotIn("category_item_groups", filters)

	def link_category_to(self, item_group):
		"""Make the fixture menu tab link one item group for this test, restoring it afterwards."""
		category = frappe.get_doc("Ecommerce Category", self.category)
		previous_link_type = category.link_type
		category.link_type = "Item Group"
		category.set("link_item_groups", [{"item_group": item_group}])
		category.save(ignore_permissions=True)
		frappe.local.commera_storefront_menu = None

		def restore():
			category.reload()
			category.link_type = previous_link_type
			category.set("link_item_groups", [])
			category.save(ignore_permissions=True)
			frappe.local.commera_storefront_menu = None

		self.addCleanup(restore)

	# -- filter / sort / pagination / count parity -----------------------------------------------

	def test_price_and_discount_filters(self):
		engine = SqliteProductSearch()
		# red effective 80 (sale), blue effective 200 (no sale).
		self.assertEqual(engine.search_products({"search": SEARCH_TOKEN, "min_price": 150}), [self.blue])
		self.assertEqual(engine.search_products({"search": SEARCH_TOKEN, "max_price": 100}), [self.red])
		self.assertEqual(engine.search_products({"search": SEARCH_TOKEN, "has_discount": 1}), [self.red])
		self.assertEqual(engine.search_count({"search": SEARCH_TOKEN, "min_price": 150}), 1)

		# Bounds arrive as strings; FTS5 columns have no type affinity, so a TEXT bound sorts above every REAL.
		self.assertEqual(engine.search_products({"search": SEARCH_TOKEN, "min_price": "150"}), [self.blue])
		self.assertEqual(engine.search_products({"search": SEARCH_TOKEN, "max_price": "100"}), [self.red])
		self.assertEqual(engine.search_count({"search": SEARCH_TOKEN, "min_price": "150"}), 1)
		# A decimal bound must survive the round trip too (the price slider posts them).
		self.assertEqual(engine.search_products({"search": SEARCH_TOKEN, "min_price": "80.5"}), [self.blue])

	def test_price_params_accept_decimals(self):
		# The price slider posts decimals; int() raised a 500 on them before they ever reached SQLite.
		from commera.www.products import list as product_list_page

		with patch.dict(frappe.form_dict, {"min": "74.5", "max": "120.25"}):
			filters = product_list_page.get_selected_filters()
		self.assertEqual(filters["min_price"], 74.5)
		self.assertEqual(filters["max_price"], 120.25)

	def test_sort_pagination_and_count_parity(self):
		engine = SqliteProductSearch()
		filters = {"search": SEARCH_TOKEN}
		self.assertEqual(
			engine.search_products(filters, sort_by="price_low", page_length=50), [self.red, self.blue]
		)
		self.assertEqual(
			engine.search_products(filters, sort_by="price_high", page_length=50), [self.blue, self.red]
		)

		page_1 = engine.search_products(filters, sort_by="price_low", page=1, page_length=1)
		page_2 = engine.search_products(filters, sort_by="price_low", page=2, page_length=1)
		self.assertEqual(page_1, [self.red])
		self.assertEqual(page_2, [self.blue])

		# The count drives the pagination controls, so it must equal the rows you can page to.
		matched = engine.search_products(filters, page_length=50)
		self.assertEqual(engine.search_count(filters), len(matched))
		self.assertEqual(len(matched), 2)

	def test_grid_preserves_engine_rank(self):
		cards = utils.get_product_list({"search": SEARCH_TOKEN})
		ranked = SqliteProductSearch().search_products({"search": SEARCH_TOKEN})
		self.assertEqual([card["name"] for card in cards], ranked)

	def test_total_count_uses_engine_for_search(self):
		self.assertEqual(utils.get_total_product_count({"search": SEARCH_TOKEN}), 2)

	# -- live price overlay ----------------------------------------------------------------------

	def test_live_price_overlay_reflects_item_price_edit(self):
		# An Item Price edit fires no Style Attribute Variant event, so the overlay must show it unrebuilt.
		price_name = self.price_names[("ZZ-RED-S", self.sale_price_list)]
		frappe.db.set_value("Item Price", price_name, "price_list_rate", 50)
		self.addCleanup(frappe.db.set_value, "Item Price", price_name, "price_list_rate", 80)

		card = search_query.build_product_cards([self.red])[0]
		self.assertEqual(card["sale_price"], 50)
		self.assertEqual(card["default_price"], 100)

	# -- one card shape across both grids ---------------------------------------------------------

	def test_both_grids_return_the_same_card_shape(self):
		# The modal is served by the index on one keystroke and frappe.qb on the next; key sets must match.
		index_card = search_query.build_product_cards([self.red])[0]
		qb_card = utils.get_product_list_qb(product_list=[self.red])[0]
		self.assertEqual(set(index_card), set(qb_card))

		# attribute_value is the shopper-facing colour on both, not the attribute's label.
		self.assertEqual(index_card["attribute_value"], "Zzred")
		self.assertEqual(qb_card["attribute_value"], "Zzred")
		self.assertEqual(qb_card["item_group"], ITEM_GROUP)
		self.assertEqual([size["size"] for size in qb_card["sizes"]], ["8", "10"])
		self.assertEqual(qb_card["effective_price"], index_card["effective_price"])
		self.assertEqual(qb_card["image"], index_card["image"])
		self.assertEqual(qb_card["hover_image"], "/files/zz-b.png")
		self.assertEqual(qb_card["hover_image"], index_card["hover_image"])

	def test_search_endpoint_shape_survives_the_grid_switch(self):
		from commera.api.utils import get_search_results

		# SEARCH_TOKEN is served by the index; the short term falls back to frappe.qb.
		indexed = get_search_results(SEARCH_TOKEN)
		# Below the FTS floor, so this one is served by the retained frappe.qb LIKE grid.
		fallback = get_search_results("Zzr")
		self.assertTrue(indexed)
		self.assertTrue(fallback)
		self.assertEqual(set(indexed[0]), set(fallback[0]))

	# -- sidebar values must round-trip back through the filter -----------------------------------

	def test_sidebar_brand_round_trips_through_both_grids(self):
		# SQLite compares the sidebar value with a BINARY-collated IN; title-casing it returned zero rows.
		from commera.search.facets import get_filter_brands

		brands = get_filter_brands({"search": SEARCH_TOKEN})
		self.assertIn(BRAND, brands)
		self.assertNotIn(BRAND.title(), brands)
		for brand in brands:
			filters = {"search": SEARCH_TOKEN, "brands": [brand]}
			self.assertTrue(SqliteProductSearch().search_products(filters))
			self.assertTrue(utils.get_product_list_qb(filters))

	# -- gotcha: unpublishing must REMOVE, not merely skip ----------------------------------------

	def test_unpublishing_removes_variant_from_index(self):
		engine = SqliteProductSearch()
		self.assertIn(self.red, engine.typeahead(SEARCH_TOKEN)["product_names"])

		self.unpublish(self.red)
		engine.index_docs("Style Attribute Variant", [self.red])

		self.assertEqual(engine.typeahead(SEARCH_TOKEN)["product_names"], [self.blue])
		self.assertEqual(engine.hydrate_cards([self.red]), [])
		self.assertEqual(
			engine.sql(
				"SELECT COUNT(*) AS count FROM search_size WHERE doc_id = ?",
				(f"Style Attribute Variant:{self.red}",),
				read_only=True,
			)[0]["count"],
			0,
		)

	def test_disabled_category_is_removed_from_index(self):
		engine = SqliteProductSearch()
		self.assertIn(self.category, engine.typeahead(SEARCH_TOKEN)["category_names"])

		frappe.db.set_value("Ecommerce Category", self.category, "enabled", 0)
		self.addCleanup(frappe.db.set_value, "Ecommerce Category", self.category, "enabled", 1)
		engine.index_docs("Ecommerce Category", [self.category])

		self.assertEqual(engine.typeahead(SEARCH_TOKEN)["category_names"], [])

	def test_index_doc_removes_a_single_unpublished_variant(self):
		engine = SqliteProductSearch()
		self.unpublish(self.red)
		engine.index_doc("Style Attribute Variant", self.red)
		self.assertNotIn(self.red, engine.typeahead(SEARCH_TOKEN)["product_names"])

	# -- gotcha: bulk frappe.db.set_value writes fire no doc event ---------------------------------

	def test_bulk_publish_hands_names_to_the_index(self):
		bulk = frappe.get_doc({"doctype": "Bulk Publish Variants", "brand": BRAND})
		for variant in (self.red, self.blue):
			self.addCleanup(frappe.db.set_value, "Style Attribute Variant", variant, "is_published", 1)
		with patch("commera.search.sync.frappe.enqueue") as enqueue:
			bulk.bulk_toggle_publish(publish=False, style_attribute_variant_list=[self.red, self.blue])

		self.assertEqual(frappe.db.get_value("Style Attribute Variant", self.red, "is_published"), 0)
		enqueue.assert_called_once()
		_args, kwargs = enqueue.call_args
		self.assertEqual(kwargs["doctype"], "Style Attribute Variant")
		self.assertEqual(set(kwargs["names"]), {self.red, self.blue})

	def test_batch_sync_is_blind_to_in_import(self):
		# An importer sets in_import then hands the set over once; honouring the flag would swallow that sync.
		with patch.dict(frappe.flags, {"in_import": True}):
			self.assertTrue(sync.skip_sync())
			self.assertFalse(sync.skip_batch_sync())

	def test_batch_sync_is_skipped_during_migrate(self):
		with patch.dict(frappe.flags, {"in_migrate": True}):
			self.assertTrue(sync.skip_batch_sync())

	def test_enqueue_upsert_many_chunks_long_name_lists(self):
		names = [f"zz-name-{index}" for index in range(record_builder.IN_CLAUSE_CHUNK_SIZE + 1)]
		with patch("commera.search.sync.frappe.enqueue") as enqueue:
			sync.enqueue_upsert_many("Style Attribute Variant", names)
		self.assertEqual(enqueue.call_count, 2)
		self.assertEqual(sum(len(call.kwargs["names"]) for call in enqueue.call_args_list), len(names))

	def test_upsert_docs_bootstraps_a_missing_index(self):
		SqliteProductSearch().drop_index()
		with patch("commera.search.sync.ensure_index_built") as ensure:
			sync.upsert_docs("Style Attribute Variant", [self.red])
		ensure.assert_called_once()

	# -- configurable content resolution -----------------------------------------------------------

	def set_content_fields(self, pairs):
		"""Point Commera Settings.search_content_fields at the given (doctype, field) pairs."""
		frappe.clear_document_cache("Commera Settings")
		self.addCleanup(frappe.clear_document_cache, "Commera Settings")
		settings = frappe.get_single("Commera Settings")
		original = [(row.search_doctype, row.field) for row in settings.search_content_fields]
		# tearDownClass commits, which would keep these rows on the site, so put the old ones back.
		self.addCleanup(self.save_content_fields, original)
		self.save_content_fields(pairs)

	def save_content_fields(self, pairs):
		frappe.clear_document_cache("Commera Settings")
		settings = frappe.get_single("Commera Settings")
		settings.search_content_fields = []
		for search_doctype, field in pairs:
			settings.append("search_content_fields", {"search_doctype": search_doctype, "field": field})
		with patch("frappe.enqueue"):
			settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Commera Settings")

	def content_for(self, variant_name):
		return record_builder.build_product_search_records([variant_name])[0]["content"]

	def test_configurator_field_flows_into_content(self):
		# An SAC field (item_attribute, reachable via variant.configurator) must reach the variant's content.
		self.set_content_fields([("Style Attribute Configurator", "item_attribute")])
		self.assertEqual(self.content_for(self.red), ITEM_ATTRIBUTE)

	def test_non_text_and_missing_fields_are_skipped(self):
		# is_published is a Check and `not_a_real_field` does not exist; both drop, leaving only Item.brand.
		self.set_content_fields(
			[
				("Item", "brand"),
				("Style Attribute Variant", "is_published"),
				("Item", "not_a_real_field"),
			]
		)
		self.assertEqual(self.content_for(self.red), BRAND)

	def test_disallowed_doctype_is_skipped(self):
		self.set_content_fields([("Item", "brand"), ("Sales Order", "customer")])
		self.assertEqual(self.content_for(self.red), BRAND)

	def test_empty_config_falls_back_to_defaults(self):
		self.set_content_fields([])
		self.assertEqual(self.content_for(self.red), f"Zzwidget Premium Red Zzred {ITEM_GROUP} {BRAND}")

	# -- install/migrate bootstrap & nightly rebuild -------------------------------------------------

	def test_ensure_index_built_noop_when_present(self):
		with patch("frappe.enqueue") as enqueue:
			build.ensure_index_built()
		enqueue.assert_not_called()

	def test_ensure_index_built_enqueues_when_absent(self):
		SqliteProductSearch().drop_index()
		with patch("frappe.enqueue") as enqueue:
			build.ensure_index_built()
		enqueue.assert_called_once()
		_args, kwargs = enqueue.call_args
		self.assertEqual(kwargs["queue"], "long")
		self.assertIs(kwargs["force"], False)
		self.assertEqual(kwargs["job_id"], SEARCH_CLASS_PATH)
		self.assertTrue(kwargs["deduplicate"])

	def test_ensure_index_built_resumes_an_interrupted_build(self):
		# A leftover temp DB is the only trace of a part-way build; without resuming, a rebuild restarts at zero.
		engine = SqliteProductSearch()
		temp_db_path = engine._get_db_path(is_temp=True)
		open(temp_db_path, "a").close()
		self.addCleanup(os.remove, temp_db_path)

		with patch("frappe.enqueue") as enqueue:
			build.ensure_index_built()
		enqueue.assert_called_once()
		_args, kwargs = enqueue.call_args
		self.assertIs(kwargs["is_continuation"], True)
		self.assertIs(kwargs["force"], True)
		self.assertEqual(kwargs["job_id"], f"{SEARCH_CLASS_PATH}_continuation")

	def test_ensure_index_built_noop_on_empty_catalogue(self):
		SqliteProductSearch().drop_index()
		with patch("frappe.db.exists", return_value=False), patch("frappe.enqueue") as enqueue:
			build.ensure_index_built()
		enqueue.assert_not_called()

	def test_nightly_rebuild_is_unconditional(self):
		# Forced rebuild leaves the index live: build_index swaps a fresh temp DB over it, so there is no pre-drop.
		with patch.object(SqliteProductSearch, "drop_index") as drop, patch("frappe.enqueue") as enqueue:
			build.rebuild_index_nightly()
		drop.assert_not_called()
		enqueue.assert_called_once()
		_args, kwargs = enqueue.call_args
		self.assertEqual(kwargs["queue"], "long")
		self.assertIs(kwargs["force"], True)

	# -- fallback safety net -------------------------------------------------------------------------

	def test_index_missing_falls_back_without_throw(self):
		SqliteProductSearch().drop_index()
		clear_search_engine()
		self.assertTrue(search_query.use_qb_fallback({"search": SEARCH_TOKEN}))
		# A live search must degrade to frappe.qb, not raise, when the index is gone.
		self.assertIsInstance(utils.get_product_list({"search": SEARCH_TOKEN}), list)

	# -- endpoint hardening --------------------------------------------------------------------------

	def test_rebuild_index_answers_with_json(self):
		with patch("frappe.enqueue", return_value=MagicMock()) as enqueue:
			response = build.rebuild_index()
		enqueue.assert_called_once()
		self.assertIsNone(response)

	def test_rebuild_index_requires_system_manager(self):
		# frappe.only_for early-returns under frappe.flags.in_test, so toggle it off to exercise the guard.
		frappe.flags.in_test = False
		try:
			frappe.set_user(NON_PRIVILEGED_USER)
			self.assertRaises(frappe.PermissionError, build.rebuild_index)
		finally:
			frappe.set_user("Administrator")
			frappe.flags.in_test = True
