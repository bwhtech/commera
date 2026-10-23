"""The tests every search-server engine must pass. Each engine's test module runs them against a live server."""

from unittest.mock import patch

import frappe

from commera import utils
from commera.api.utils import get_search_results
from commera.search import query as search_query
from commera.search.catalogue_fixtures import (
	ITEM_GROUP,
	ITEM_GROUP_BLUE,
	SEARCH_TOKEN,
	STYLE_ITEM,
	SearchCatalogue,
)
from commera.search.engine import CARD_COLUMNS
from commera.search.engine_cache import clear_search_engine
from commera.search.http_client import SearchServerError
from commera.search.typeahead import get_typeahead

INDEX_PREFIX = "commera_test_search"


class RemoteEngineTests(SearchCatalogue):
	# Set by each engine's test class: the engine class and the live server to test against.
	ENGINE = None
	URL = None
	KEY = None

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		settings = frappe.get_cached_doc("Commera Settings")
		cls.default_price_list = settings.default_price_list
		cls.sale_price_list = settings.sale_price_list
		cls.price_names = {}

		cls.drop_catalogue()
		cls.build_catalogue()
		# Fixtures outlive one test method, so they are committed and torn down explicitly.
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		cls.new_engine().rebuild()

	@classmethod
	def tearDownClass(cls):
		cls.new_engine().drop_index()
		cls.drop_catalogue()
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		super().tearDownClass()

	def setUp(self):
		clear_search_engine()
		self.engine = self.new_engine()

	@classmethod
	def new_engine(cls):
		return cls.ENGINE(cls.URL, cls.KEY, INDEX_PREFIX)

	def wait_for_writes(self):
		"""Wait until the server has applied the writes sent so far. Engines that write synchronously need not."""

	def leftover_indexes(self):
		"""Indexes a rebuild left behind on the server."""
		raise NotImplementedError

	def grid(self, sort_by="default", **filters):
		return self.engine.search_products(
			{"search": SEARCH_TOKEN, **filters}, page_length=50, sort_by=sort_by
		)

	# -- what SQLite cannot do -------------------------------------------------------------------

	def test_short_terms_and_typos_are_served(self):
		# SQLite needs 4 characters and sends the rest to frappe.qb; a search server ranks any term.
		self.assertTrue(self.engine.can_rank("zz"))
		self.assertEqual(
			set(self.engine.search_products({"search": "zzw"})), {self.red, self.blue, self.green}
		)
		self.assertIn(self.red, self.engine.search_products({"search": "zzwidgte"}))

	# -- grid, sort, filters ---------------------------------------------------------------------

	def test_grid_and_count(self):
		self.assertEqual(set(self.grid()), {self.red, self.blue, self.green})
		self.assertEqual(self.engine.search_count({"search": SEARCH_TOKEN}), 3)
		self.assertEqual(self.engine.search_products({"search": "zzwidget premium red"}), [self.red])

	def test_sorts_order_the_whole_grid(self):
		# Effective prices: red 80 (on sale), green 150, blue 200.
		self.assertEqual(self.grid("price_low"), [self.red, self.green, self.blue])
		self.assertEqual(self.grid("price_high"), [self.blue, self.green, self.red])
		self.assertEqual(self.grid("name"), [self.blue, self.green, self.red])

	def test_pagination(self):
		pages = [
			self.engine.search_products(
				{"search": SEARCH_TOKEN}, page=page, page_length=2, sort_by="price_low"
			)
			for page in (1, 2)
		]
		self.assertEqual(pages, [[self.red, self.green], [self.blue]])

	def test_filters(self):
		self.assertEqual(self.grid(subcategory=[ITEM_GROUP_BLUE]), [self.blue])
		self.assertEqual(self.grid(sizes=["8"]), [self.red])
		self.assertEqual(self.grid(has_discount=True), [self.red])
		self.assertEqual(self.grid("price_low", min_price=100), [self.green, self.blue])
		self.assertEqual(self.grid(max_price=80.5), [self.red])
		self.assertEqual(self.grid(category_item_groups=[ITEM_GROUP_BLUE]), [self.blue])

	# -- facets ----------------------------------------------------------------------------------

	def test_each_facet_ignores_only_its_own_filter(self):
		facets = self.engine.facet_counts({"search": SEARCH_TOKEN, "sizes": ["8"]})
		self.assertEqual(facets["category"], {ITEM_GROUP: 1})
		self.assertEqual(list(facets["size"]), ["8", "10", "38", "40", "ZS"])

	def test_category_scope_holds_in_every_facet(self):
		facets = self.engine.facet_counts(
			{
				"search": SEARCH_TOKEN,
				"category_item_groups": [ITEM_GROUP_BLUE],
				"subcategory": [ITEM_GROUP_BLUE],
			}
		)
		self.assertEqual(facets["category"], {ITEM_GROUP_BLUE: 1})
		self.assertEqual(list(facets["size"]), ["38", "40"])

	def test_typeahead_returns_products_and_categories(self):
		result = self.engine.typeahead(SEARCH_TOKEN, limit=2)
		self.assertEqual(len(result["product_names"]), 2)
		self.assertEqual(result["category_names"], [self.category])

	def test_hyphenated_words_match_each_part(self):
		frappe.db.set_value("Style Attribute Variant", self.red, "display_name", "Zzwidget All-Weather Red")
		self.addCleanup(self.restore_display_name, self.red, "Zzwidget Premium Red")
		self.engine.index_docs("Style Attribute Variant", [self.red])
		self.wait_for_writes()
		self.assertEqual(self.engine.search_products({"search": "zzwidget weather"}), [self.red])

	def restore_display_name(self, variant, display_name):
		frappe.db.set_value("Style Attribute Variant", variant, "display_name", display_name)
		self.engine.index_docs("Style Attribute Variant", [variant])
		self.wait_for_writes()

	# -- cards -----------------------------------------------------------------------------------

	def test_hydrated_cards_keep_order_and_shape(self):
		cards = self.engine.hydrate_cards([self.blue, self.red, "no such variant"])
		self.assertEqual([card["name"] for card in cards], [self.blue, self.red])
		self.assertEqual(set(CARD_COLUMNS) - set(cards[0]), set())
		self.assertEqual([size["size"] for size in cards[0]["sizes"]], ["38", "40"])

	# -- incremental writes ----------------------------------------------------------------------

	def test_unpublishing_removes_and_republishing_restores(self):
		self.unpublish(self.red)
		self.engine.index_doc("Style Attribute Variant", self.red)
		self.wait_for_writes()
		self.assertEqual(set(self.grid()), {self.blue, self.green})

		frappe.db.set_value("Style Attribute Variant", self.red, "is_published", 1)
		self.engine.index_docs("Style Attribute Variant", [self.red])
		self.wait_for_writes()
		self.assertEqual(set(self.grid()), {self.red, self.blue, self.green})

	def test_rebuild_leaves_no_temporary_index(self):
		self.engine.rebuild()
		self.assertEqual(self.leftover_indexes(), [])
		self.assertEqual(set(self.grid()), {self.red, self.blue, self.green})

	# -- the storefront on a search server -----------------------------------------------------------

	def test_storefront_uses_the_engine_for_short_terms(self):
		with patch("commera.search.engine_cache.new_search_engine", return_value=self.engine):
			self.assertFalse(search_query.use_qb_fallback({"search": "zz"}))
			grid = utils.get_product_list({"search": "zzw"}, sort_by="price_low")
			self.assertEqual([card["name"] for card in grid], [self.red, self.green, self.blue])
			self.assertEqual(utils.get_total_product_count({"search": "zzw"}), 3)
			self.assertEqual(len(get_search_results("zzw")), 3)

	def test_typeahead_ranks_short_terms_and_links_categories(self):
		frappe.local.commera_storefront_menu = None
		with patch("commera.search.engine_cache.new_search_engine", return_value=self.engine):
			result = get_typeahead("zzw")
		self.assertEqual({card["name"] for card in result["products"]}, {self.red, self.blue, self.green})
		self.assertEqual([category["name"] for category in result["categories"]], [self.category])

	def test_arabic_item_names_are_searchable(self):
		if not frappe.db.has_column("Item", "custom_item_name_ar"):
			self.skipTest("Item has no custom_item_name_ar field on this site")
		variants = [self.red, self.blue, self.green]
		frappe.db.set_value("Item", STYLE_ITEM, "custom_item_name_ar", "ودجت تجريبي")
		self.engine.index_docs("Style Attribute Variant", variants)
		self.wait_for_writes()

		def restore():
			frappe.db.set_value("Item", STYLE_ITEM, "custom_item_name_ar", None)
			self.engine.index_docs("Style Attribute Variant", variants)
			self.wait_for_writes()

		self.addCleanup(restore)
		self.assertEqual(set(self.engine.typeahead("ودجت")["product_names"]), set(variants))

	# -- requests per page -----------------------------------------------------------------------

	def test_a_ready_index_costs_no_request(self):
		# The rebuild recorded readiness in the site cache, so a page load must not ask the server again.
		engine = self.new_engine()
		with patch.object(engine.client, "get", side_effect=AssertionError("asked the server")):
			self.assertTrue(engine.index_exists())

	def test_the_grid_answer_supplies_the_count(self):
		self.engine.search_products({"search": SEARCH_TOKEN, "colors": ["Zzred"]})
		with patch.object(self.engine.client, "post", side_effect=AssertionError("asked again")):
			self.assertEqual(self.engine.search_count({"search": SEARCH_TOKEN, "colors": ["Zzred"]}), 1)
		# A different query still asks the server.
		self.assertEqual(self.engine.search_count({"search": SEARCH_TOKEN}), 3)

	def test_unreachable_server_falls_back_to_qb(self):
		down = self.ENGINE("http://127.0.0.1:9", self.KEY, INDEX_PREFIX)
		self.addCleanup(frappe.cache.delete_value, down.ready_key)
		self.addCleanup(frappe.cache.delete_value, down.client.down_key)
		with patch("commera.search.engine_cache.new_search_engine", return_value=down):
			self.assertTrue(search_query.use_qb_fallback({"search": SEARCH_TOKEN}))
			self.assertIsInstance(utils.get_product_list({"search": SEARCH_TOKEN}), list)

		# Later requests trust the down marker instead of trying again.
		frappe.cache.delete_value(down.ready_key)
		again = self.ENGINE("http://127.0.0.1:9", self.KEY, INDEX_PREFIX)
		with patch.object(again.client.session, "request", side_effect=AssertionError("retried")):
			self.assertFalse(again.index_exists())

	def test_the_first_request_of_an_outage_is_served_from_qb(self):
		# The engine trusts its cached readiness, so it only learns of the outage from a failed search.
		down = self.ENGINE("http://127.0.0.1:9", self.KEY, INDEX_PREFIX)
		down.remember_readiness(True)
		self.addCleanup(frappe.cache.delete_value, down.ready_key)
		self.addCleanup(frappe.cache.delete_value, down.client.down_key)
		with patch("commera.search.engine_cache.new_search_engine", return_value=down):
			filters = {"search": SEARCH_TOKEN}
			self.assertEqual(
				{card["name"] for card in utils.get_product_list(filters)}, {self.red, self.blue, self.green}
			)
			self.assertEqual(utils.get_total_product_count(filters), 3)
			self.assertIsNone(search_query.listing_facets(filters))
			self.assertEqual(len(get_typeahead(SEARCH_TOKEN)["products"]), 3)

	def test_settings_reject_a_bad_key(self):
		self.assertRaises(SearchServerError, self.ENGINE.check_connection, self.URL, "not-the-key")
		self.ENGINE.check_connection(self.URL, self.KEY)
