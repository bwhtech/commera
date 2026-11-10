import difflib
import os
import sqlite3
from contextlib import closing
from typing import ClassVar

import frappe
from frappe.search.sqlite_search import (
	MAX_EDIT_DISTANCE,
	MAX_RERANK_CANDIDATES,
	MIN_WORD_LENGTH,
	SQLiteSearch,
	strip_surrogates,
)
from frappe.utils import create_batch, flt

from commera.localization.content import SHOP_WIDE
from commera.localization.languages import StorefrontLanguages
from commera.search.arabic import arabic_search_forms, arabic_word_forms, is_arabic_query
from commera.search.build_writes import reconcile_build_writes, track_build_writes
from commera.search.engine import (
	CARD_COLUMNS,
	MIN_QUERY_LENGTH,
	SearchEngineBase,
	empty_facets,
	empty_typeahead,
	is_query_too_short,
)
from commera.search.price_markets import PRICE_COLUMNS, get_price_market, get_price_markets
from commera.search.record_builder import (
	build_category_search_records,
	build_product_search_records,
)
from commera.search.translations import (
	get_search_markets,
	index_generation,
	rebuild_if_generation_changes,
)

CATEGORY_DOCTYPE = "Ecommerce Category"
FACET_COLUMN_TO_KEY = {"brand": "brand", "color": "color", "item_group": "category"}

# SQLite caps bound parameters per statement (999 on older builds), so bulk deletes go out in chunks.
SQLITE_PARAM_CHUNK_SIZE = 500

# Ceiling for the edit-distance fallback below; beyond 2 edits the "correction" is a different word.
MAX_EDIT_DISTANCE_FALLBACK = 2

SEARCH_CLASS_PATH = "commera.search.sqlite_product_search.SqliteProductSearch"
CORE_BUILD_INDEX = "frappe.search.sqlite_search.build_index"
BUILD_TIMEOUT = 2 * 60 * 60 + 10 * 60

ARABIC_SCRIPT_LANGUAGES = {"ar", "fa", "ur"}
# Sorts after every character, so `word < prefix + LAST_CHARACTER` bounds a prefix range.
LAST_CHARACTER = "\U0010ffff"


class SqliteProductSearch(SQLiteSearch, SearchEngineBase):
	INDEX_NAME = "commera_product_search.db"

	INDEX_SCHEMA: ClassVar = {
		"text_fields": ["title", "content"],
		# `market` is "" on a record's own row. A market row swaps its title for that market's titles.
		# Prices live in search_price, one row per product and market.
		"metadata_fields": ["item_group", "brand", "color", "route_slug", "market"],
		"tokenizer": "unicode61 remove_diacritics 2",
	}

	PRODUCT_DETAIL_COLUMNS: ClassVar = ("doc_id", *CARD_COLUMNS)

	INDEXABLE_DOCTYPES: ClassVar = {
		"Style Attribute Variant": {
			"fields": [
				"name",
				{"title": "display_name"},
				{"content": "display_name"},
				"item_group",
			],
			"filters": {"is_published": 1},
		},
		"Ecommerce Category": {
			"fields": [
				"name",
				{"title": "category_name"},
				{"content": "category_name"},
			],
			"filters": {"enabled": 1},
		},
	}

	RECORD_BUILDERS: ClassVar = {
		"Style Attribute Variant": build_product_search_records,
		"Ecommerce Category": build_category_search_records,
	}

	def get_search_filters(self):
		return {"market": get_search_markets()}

	def can_rank(self, term):
		"""True for a term of at least MIN_QUERY_LENGTH, once the index exists.
		An Arabic term also needs an Arabic language in the index, else frappe.qb serves it."""
		term = (term or "").strip()
		if len(term) < MIN_QUERY_LENGTH or not self.index_exists():
			return False
		if not self.prices_market(get_price_market()):
			return False
		return not is_arabic_query(term) or self.indexes_arabic()

	def prices_market(self, key):
		"""Whether the build priced the market `key`. A newer market waits for the rebuild it enqueued."""
		cached = getattr(self, "price_markets_cache", None)
		if cached is None:
			rows = self.sql("SELECT market FROM search_price_market", read_only=True)
			cached = self.price_markets_cache = {row["market"] for row in rows}
		return key in cached

	def indexes_arabic(self):
		"""Whether the index holds a language in Arabic script, memoized like index_exists()."""
		cached = getattr(self, "indexes_arabic_cache", None)
		if cached is None:
			rows = self.sql("SELECT code FROM search_language", read_only=True)
			cached = any(row["code"].split("-")[0].lower() in ARABIC_SCRIPT_LANGUAGES for row in rows)
			self.indexes_arabic_cache = cached
		return cached

	# -- index shape ----------------------------------------------------------------------------

	def index_exists(self):
		"""Whether a current-shape index is present, memoized for this instance."""
		# Read paths share one request-scoped instance; write/build paths use fresh ones, so it never goes stale.
		cached = getattr(self, "index_exists_cache", None)
		if cached is None:
			cached = (
				super().index_exists()
				and self._table_exists("product_detail")
				and self._table_exists("search_language")
				and self._table_exists("search_price")
				and self._table_exists("search_price_market")
				and self.fts_has_columns(("market",))
			)
			self.index_exists_cache = cached
		return cached

	def fts_has_columns(self, columns):
		try:
			rows = self.sql("PRAGMA table_info(search_fts)", read_only=True)
		except sqlite3.Error:
			return False
		existing = {row["name"] for row in rows}
		return all(column in existing for column in columns)

	def _ensure_fts_table(self):
		super()._ensure_fts_table()
		self._with_connection(self.create_sibling_tables)

	def create_sibling_tables(self, cursor):
		cursor.execute("CREATE TABLE IF NOT EXISTS search_size (doc_id TEXT, size TEXT, item_code TEXT)")
		cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_size_doc ON search_size(doc_id)")

		# The published languages whose titles this build indexed.
		cursor.execute("CREATE TABLE IF NOT EXISTS search_language (code TEXT PRIMARY KEY)")
		cursor.execute("DELETE FROM search_language")
		codes = [(language.code,) for language in StorefrontLanguages.load().published]
		cursor.executemany("INSERT INTO search_language (code) VALUES (?)", codes)
		# The languages and prices the build started with. A resumed build restarts when they changed.
		cursor.execute("CREATE TABLE IF NOT EXISTS search_generation (generation TEXT)")
		cursor.execute("DELETE FROM search_generation")
		generation = getattr(self, "build_generation", None) or index_generation()
		cursor.execute("INSERT INTO search_generation (generation) VALUES (?)", (generation,))

		self.create_price_tables(cursor)

		columns = ",\n".join(self.product_detail_column_defs())
		cursor.execute(f"CREATE TABLE IF NOT EXISTS product_detail ({columns})")
		for column in (
			"modified",
			"display_name",
			"item_group",
			"brand",
			"color",
		):
			cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_pd_{column} ON product_detail({column})")

	def create_price_tables(self, cursor):
		cursor.execute(
			"CREATE TABLE IF NOT EXISTS search_price (doc_id TEXT, market TEXT, effective_price REAL, "
			"sale_price REAL, default_price REAL, discount_percent REAL, has_discount INTEGER, "
			"sale_end_date TEXT, PRIMARY KEY (market, doc_id))"
		)
		cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_price_doc ON search_price(doc_id)")
		# The markets this build prices. A search in any other market is served by frappe.qb.
		cursor.execute("CREATE TABLE IF NOT EXISTS search_price_market (market TEXT PRIMARY KEY)")
		cursor.execute("DELETE FROM search_price_market")
		markets = [(key,) for key in get_price_markets()]
		cursor.executemany("INSERT INTO search_price_market (market) VALUES (?)", markets)

	def product_detail_column_defs(self):
		integer_columns = {"is_stock_item", "has_discount"}
		real_columns = {"default_price", "sale_price", "effective_price", "discount_percent"}
		definitions = []
		for column in self.PRODUCT_DETAIL_COLUMNS:
			if column == "doc_id":
				definitions.append("doc_id TEXT PRIMARY KEY")
			elif column in real_columns:
				definitions.append(f"{column} REAL")
			elif column in integer_columns:
				definitions.append(f"{column} INTEGER")
			else:
				definitions.append(f"{column} TEXT")
		return definitions

	# -- builds ---------------------------------------------------------------------------------

	def build_index(self, batch_size=1000, is_continuation=False):
		track_build_writes()
		self.build_generation = generation = index_generation()
		if is_continuation and self.stored_generation() != generation:
			# The finished batches hold the old languages' titles or the old prices.
			self.discard_partial_build()
			is_continuation = False
		super().build_index(batch_size=batch_size, is_continuation=is_continuation)
		frappe.db.after_commit.add(reconcile_build_writes)
		rebuild_if_generation_changes(self, generation, SEARCH_CLASS_PATH)

	def stored_generation(self):
		"""The index generation the build being resumed started with, or None."""
		temp_path = self._get_db_path(is_temp=True)
		path = temp_path if os.path.exists(temp_path) else self.db_path
		if not os.path.exists(path):
			return None
		try:
			with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as connection:
				row = connection.execute("SELECT generation FROM search_generation").fetchone()
		except sqlite3.Error:
			return None
		return row[0] if row else None

	def discard_partial_build(self):
		temp_path = self._get_db_path(is_temp=True)
		if os.path.exists(temp_path):
			os.unlink(temp_path)

	def enqueue_full_rebuild(self, deduplicate=False):
		"""Enqueue a full rebuild on the long queue. Returns the enqueue payload."""
		# Core builds into a temp DB and renames it over the live one, so the index keeps serving.
		track_build_writes()
		return frappe.enqueue(
			CORE_BUILD_INDEX,
			queue="long",
			enqueue_after_commit=True,
			timeout=BUILD_TIMEOUT,
			job_id=SEARCH_CLASS_PATH if deduplicate else None,
			deduplicate=deduplicate,
			search_class_path=SEARCH_CLASS_PATH,
			force=True,
		)

	def ensure_index_built(self):
		"""Build the index when it is absent, or resume a build that died part-way through."""
		# No sqlite_search hook here, so core's own resume never sees this index; a leftover temp DB is
		# the only trace of an interrupted build.
		is_continuation = os.path.exists(self._get_db_path(is_temp=True))
		if self.index_exists() and not is_continuation:
			return None
		if not frappe.db.exists("Style Attribute Variant", {"is_published": 1}):
			return None
		return frappe.enqueue(
			CORE_BUILD_INDEX,
			queue="long",
			enqueue_after_commit=True,
			timeout=BUILD_TIMEOUT,
			job_id=f"{SEARCH_CLASS_PATH}_continuation" if is_continuation else SEARCH_CLASS_PATH,
			deduplicate=True,
			search_class_path=SEARCH_CLASS_PATH,
			force=is_continuation,
			is_continuation=is_continuation,
		)

	# -- record overlay -------------------------------------------------------------------------

	def build_records_for(self, doctype, names):
		builder = self.RECORD_BUILDERS.get(doctype)
		records = builder(names) if builder else []
		return {record["name"]: record for record in records}

	def overlay_records(self, docs, records):
		for doc in docs:
			record = records.get(doc.name)
			if not record:
				doc.search_content = ""
				continue
			doc.search_content = record.get("content") or ""
			doc.market_titles = record.get("market_titles") or {}
			doc.brand = record.get("brand") or ""
			doc.color = record.get("color") or ""
			doc.item_group = record.get("item_group") or doc.get("item_group") or ""
			doc.route_slug = record.get("route_slug") or ""
			doc.sizes = record.get("sizes") or []
			doc.product_detail = record.get("detail")
			doc.market_prices = record.get("market_prices") or {}

	def get_documents_paginated(
		self, doctype, limit=1000, last_indexed_modified=None, last_indexed_name=None
	):
		docs = super().get_documents_paginated(
			doctype,
			limit=limit,
			last_indexed_modified=last_indexed_modified,
			last_indexed_name=last_indexed_name,
		)
		if not docs:
			return docs
		records = self.build_records_for(doctype, [doc.name for doc in docs])
		self.overlay_records(docs, records)
		return docs

	def prepare_document(self, doc):
		document = super().prepare_document(doc)
		if document:
			content = getattr(doc, "search_content", document.get("content", ""))
			document["content"] = searchable_content(document.get("title"), content)
			document["market"] = SHOP_WIDE
			document["_own_content"] = content
			document["_market_titles"] = getattr(doc, "market_titles", None) or {}
			document["_sizes"] = getattr(doc, "sizes", None) or []
			document["_detail"] = getattr(doc, "product_detail", None)
			document["_market_prices"] = getattr(doc, "market_prices", None) or {}
		return document

	# -- incremental writes ---------------------------------------------------------------------

	def index_doc(self, doctype, docname):
		"""Rebuild and write one doc's index rows directly."""
		# Not core's queue path: it re-reads the doc without the record overlay and wipes product_detail rows.
		self.raise_if_not_indexed()
		records = self.build_records_for(doctype, [docname])
		record = records.get(docname)
		if not record:
			self.remove_doc(doctype, docname)
			return
		self._index_documents(self.documents_for(doctype, [docname], records))

	def index_docs(self, doctype, names):
		"""Re-sync many docs at once: one batched record build, one FTS write, one delete pass."""
		self.raise_if_not_indexed()
		names = list(names)
		if not names:
			return

		records = self.build_records_for(doctype, names)
		self._index_documents(self.documents_for(doctype, names, records))
		self.remove_docs(doctype, [name for name in names if name not in records])

	def documents_for(self, doctype, names, records):
		"""Indexable documents for the names that produced a record, overlaid with their record data."""
		config = self.doc_configs[doctype]
		docs = []
		for name in names:
			record = records.get(name)
			if not record:
				continue
			doc = frappe._dict(doctype=doctype, name=name)
			doc[config["title_field"]] = record["title"]
			doc[config["content_field"]] = record["title"]
			docs.append(doc)

		self.overlay_records(docs, records)
		return [document for document in (self.prepare_document(doc) for doc in docs) if document]

	def _index_documents(self, documents):
		super()._index_documents(documents)

		def index_siblings(cursor):
			for document in documents:
				doc_id = document.get("id")
				if not doc_id:
					continue
				self.write_search_size(cursor, doc_id, document.get("_sizes") or [])
				self.write_product_detail(cursor, doc_id, document.get("_detail"))
				self.write_search_prices(cursor, doc_id, document.get("_market_prices") or {})
			self.write_market_rows(cursor, documents)

		self._with_connection(index_siblings)

	def write_market_rows(self, cursor, documents):
		"""A row per market title of each document. Core's write deleted the old ones with its doc_id."""
		fields = ["doc_id", *self.schema["text_fields"], *self.schema["metadata_fields"]]
		rows = [
			tuple(strip_surrogates(row.get(field, "")) for field in fields)
			for document in documents
			for row in market_rows(document)
		]
		if rows:
			placeholders = ", ".join("?" for _ in fields)
			cursor.executemany(f"INSERT INTO search_fts ({', '.join(fields)}) VALUES ({placeholders})", rows)

	def write_search_size(self, cursor, doc_id, sizes):
		cursor.execute("DELETE FROM search_size WHERE doc_id = ?", (doc_id,))
		rows = [(doc_id, size.get("size") or "", size.get("item_code") or "") for size in sizes]
		if rows:
			cursor.executemany("INSERT INTO search_size (doc_id, size, item_code) VALUES (?, ?, ?)", rows)

	def write_search_prices(self, cursor, doc_id, market_prices):
		cursor.execute("DELETE FROM search_price WHERE doc_id = ?", (doc_id,))
		columns = ("doc_id", "market", *PRICE_COLUMNS)
		rows = [
			(doc_id, market, *(prices.get(column) for column in PRICE_COLUMNS))
			for market, prices in market_prices.items()
		]
		if rows:
			placeholders = ", ".join("?" for _ in columns)
			cursor.executemany(
				f"INSERT INTO search_price ({', '.join(columns)}) VALUES ({placeholders})", rows
			)

	def write_product_detail(self, cursor, doc_id, detail):
		cursor.execute("DELETE FROM product_detail WHERE doc_id = ?", (doc_id,))
		if not detail:
			return
		row = {**detail, "doc_id": doc_id}
		columns = self.PRODUCT_DETAIL_COLUMNS
		placeholders = ", ".join("?" for _ in columns)
		values = tuple(row.get(column) for column in columns)
		cursor.execute(
			f"INSERT INTO product_detail ({', '.join(columns)}) VALUES ({placeholders})",
			values,
		)

	def remove_doc(self, doctype, docname):
		super().remove_doc(doctype, docname)
		doc_id = f"{doctype}:{docname}"
		self.sql("DELETE FROM search_size WHERE doc_id = ?", (doc_id,), commit=True)
		self.sql("DELETE FROM product_detail WHERE doc_id = ?", (doc_id,), commit=True)
		self.sql("DELETE FROM search_price WHERE doc_id = ?", (doc_id,), commit=True)

	def remove_docs(self, doctype, names):
		"""Drop many docs from the FTS table and its sibling tables."""
		self.raise_if_not_indexed()
		for chunk in create_batch(list(names), SQLITE_PARAM_CHUNK_SIZE):
			doc_ids = tuple(f"{doctype}:{name}" for name in chunk)
			placeholders = ", ".join("?" for _ in doc_ids)
			for table in ("search_fts", "search_size", "product_detail", "search_price"):
				self.sql(f"DELETE FROM {table} WHERE doc_id IN ({placeholders})", doc_ids, commit=True)

	# -- card hydration -------------------------------------------------------------------------

	def hydrate_cards(self, names):
		"""Card dicts for the given variant names, in `names` order, from product_detail + search_size."""
		if not names:
			return []

		card_by_name = {}
		sizes_by_name = {}
		prices_by_name = {}
		market = get_price_market()
		# Chunked: SQLite caps bound parameters per statement, and nothing bounds the caller's name list.
		for chunk in create_batch(list(names), SQLITE_PARAM_CHUNK_SIZE):
			doc_ids = tuple(f"Style Attribute Variant:{name}" for name in chunk)
			placeholders = ", ".join("?" for _ in doc_ids)

			for row in self.sql(
				f"SELECT * FROM product_detail WHERE doc_id IN ({placeholders})",
				doc_ids,
				read_only=True,
			):
				card_by_name[row["name"]] = {key: row[key] for key in row.keys() if key != "doc_id"}

			for row in self.sql(
				f"SELECT doc_id, size, item_code FROM search_size WHERE doc_id IN ({placeholders})",
				doc_ids,
				read_only=True,
			):
				name = row["doc_id"].split(":", 1)[1]
				sizes_by_name.setdefault(name, []).append(
					{"size": row["size"], "item_code": row["item_code"]}
				)

			for row in self.sql(
				f"SELECT * FROM search_price WHERE market = ? AND doc_id IN ({placeholders})",
				(market, *doc_ids),
				read_only=True,
			):
				name = row["doc_id"].split(":", 1)[1]
				prices_by_name[name] = {column: row[column] for column in PRICE_COLUMNS}

		cards = []
		for name in names:
			card = card_by_name.get(name)
			if not card:
				continue
			card["sizes"] = sizes_by_name.get(name, [])
			# product_detail holds the store prices; a product its market cannot price has none.
			card.update(prices_by_name.get(name) or dict.fromkeys(PRICE_COLUMNS))
			cards.append(card)
		return cards

	# -- facets ---------------------------------------------------------------------------------

	NARROW_KEY_TO_COLUMN: ClassVar = {
		"subcategory": "item_group",
		"brands": "brand",
		"colors": "color",
	}

	COLUMN_TO_NARROW_KEY: ClassVar = {column: key for key, column in NARROW_KEY_TO_COLUMN.items()}

	def count_facets(self, fts_query, filters=None):
		"""Sidebar counts per facet, each narrowed by every OTHER selected filter but not by its own."""
		# Must match the frappe.qb sidebar: www/products/list.py pops the facet's own key before querying.
		selected = filters or {}
		counts = {}
		for column, key in FACET_COLUMN_TO_KEY.items():
			narrow_sql, narrow_params = self.narrow_clause(selected, self.COLUMN_TO_NARROW_KEY[column])
			rows = self.sql(
				f"SELECT {column} AS value, COUNT(DISTINCT doc_id) AS count FROM search_fts "
				f"WHERE search_fts MATCH ? AND {column} IS NOT NULL AND {column} != ''{narrow_sql} "
				f"GROUP BY {column} ORDER BY count DESC",
				(fts_query, *narrow_params),
				read_only=True,
			)
			counts[key] = {row["value"]: row["count"] for row in rows}
		counts["size"] = self.size_facet_counts(fts_query, selected)
		return counts

	def size_facet_counts(self, fts_query, filters=None):
		narrow_sql, narrow_params = self.narrow_clause(filters or {}, "sizes")
		rows = self.sql(
			"SELECT size, COUNT(DISTINCT doc_id) AS count FROM search_size "
			"WHERE size != '' AND doc_id IN "
			f"(SELECT doc_id FROM search_fts WHERE search_fts MATCH ?{narrow_sql}) "
			# Sizes sort numerically to match the frappe.qb sidebar's Cast_(size, "Decimal"); label breaks ties.
			"GROUP BY size ORDER BY CAST(size AS REAL), size",
			(fts_query, *narrow_params),
			read_only=True,
		)
		return {row["size"]: row["count"] for row in rows}

	def narrow_clause(self, selected, drop_key, prefix=""):
		markets = get_search_markets()
		clauses = [f" AND {prefix}market IN ({', '.join('?' for _ in markets)})"]
		params = list(markets)
		for narrow_key, column in self.NARROW_KEY_TO_COLUMN.items():
			if narrow_key == drop_key:
				continue
			values = selected.get(narrow_key)
			if not values:
				continue
			placeholders = ", ".join("?" for _ in values)
			clauses.append(f" AND {prefix}{column} IN ({placeholders})")
			params.extend(values)
		# The ?category= tab scope is not a facet: no facet drops it, so it narrows every count too.
		if selected.get("category_item_groups"):
			placeholders = ", ".join("?" for _ in selected["category_item_groups"])
			clauses.append(f" AND {prefix}item_group IN ({placeholders})")
			params.extend(selected["category_item_groups"])
		if drop_key != "sizes" and selected.get("sizes"):
			placeholders = ", ".join("?" for _ in selected["sizes"])
			clauses.append(
				f" AND {prefix}doc_id IN (SELECT doc_id FROM search_size WHERE size IN ({placeholders}))"
			)
			params.extend(selected["sizes"])
		price_sql, price_params = self.price_clause(selected, prefix)
		clauses.append(price_sql)
		params.extend(price_params)
		return "".join(clauses), params

	def price_clause(self, filters, prefix=""):
		"""Products priced in the request's market, within the min_price/max_price/has_discount filters.
		Menu entries have no price, so they always pass."""
		conditions = ["market = ?"]
		params = [get_price_market()]
		# flt() the bounds: a query string may send "" or text.
		if min_price := flt(filters.get("min_price")):
			conditions.append("effective_price >= ?")
			params.append(min_price)
		if max_price := flt(filters.get("max_price")):
			conditions.append("effective_price <= ?")
			params.append(max_price)
		if filters.get("has_discount"):
			conditions.append("has_discount = 1")
		priced = f"SELECT doc_id FROM search_price WHERE {' AND '.join(conditions)}"
		return f" AND ({prefix}doctype = ? OR {prefix}doc_id IN ({priced}))", [CATEGORY_DOCTYPE, *params]

	# -- search grid ----------------------------------------------------------------------------

	def detail_order(self, sort_by):
		"""ORDER BY fragment over the product and its market prices; `name` breaks ties so pages never overlap."""
		columns = {
			"price_low": "search_price.effective_price ASC",
			"price_high": "search_price.effective_price DESC",
			"name": "product_detail.display_name ASC",
			"new_arrival": "product_detail.modified DESC",
			"discount": "search_price.discount_percent DESC",
		}
		primary = columns.get(sort_by)
		return f"{primary}, product_detail.name ASC" if primary else "product_detail.name ASC"

	def _prepare_fts_query(self, query):
		"""Core's FTS5 query, where an Arabic word matches any of its forms."""
		# A NUL inside a quoted term makes SQLite report an unterminated string.
		query = query.replace("\x00", "")
		if not is_arabic_query(query):
			return super()._prepare_fts_query(query)
		# FTS5 rejects an implicit AND next to a bracketed group, so AND is explicit.
		return " AND ".join(self.fts_term(word) for word in query.split())

	def fts_term(self, word):
		phrases = [fts_phrase(form) for form in arabic_word_forms(word)]
		return phrases[0] if len(phrases) == 1 else f"({' OR '.join(phrases)})"

	def fts_query_for(self, term):
		"""Expanded + escaped FTS5 MATCH string for a term, or "" when too short / index missing."""
		if is_query_too_short(term) or not self.index_exists():
			return ""
		expanded_query, _corrections = self._expand_query_with_corrections(term)
		return self._prepare_fts_query(expanded_query)

	def search_products(self, filters, page=1, page_length=30, sort_by="default"):
		"""Variant names for a text search page: FTS-matched, filtered, sorted, paginated."""
		fts_query = self.fts_query_for((filters.get("search") or "").strip())
		if not fts_query:
			return []
		where, params = self.narrow_clause(filters, None, prefix="search_fts.")
		# A product can match through its own row and its market's. The hidden `rank` is bm25, and
		# unlike bm25() it may be aggregated.
		order = "MIN(search_fts.rank), product_detail.name ASC"
		if sort_by != "default":
			order = self.detail_order(sort_by)
		offset = (page - 1) * page_length
		rows = self.sql(
			"SELECT product_detail.name AS name FROM search_fts "
			"JOIN product_detail ON product_detail.doc_id = search_fts.doc_id "
			"JOIN search_price ON search_price.doc_id = search_fts.doc_id AND search_price.market = ? "
			f"WHERE search_fts MATCH ?{where} GROUP BY product_detail.name "
			f"ORDER BY {order} LIMIT ? OFFSET ?",
			(get_price_market(), fts_query, *params, page_length, offset),
			read_only=True,
		)
		return [row["name"] for row in rows]

	def search_count(self, filters):
		"""Total variants matching a text search + its filters (true count, not capped — count parity)."""
		fts_query = self.fts_query_for((filters.get("search") or "").strip())
		if not fts_query:
			return 0
		where, params = self.narrow_clause(filters, None, prefix="search_fts.")
		rows = self.sql(
			"SELECT COUNT(DISTINCT product_detail.name) AS count FROM search_fts "
			"JOIN product_detail ON product_detail.doc_id = search_fts.doc_id "
			f"WHERE search_fts MATCH ?{where}",
			(fts_query, *params),
			read_only=True,
		)
		return rows[0]["count"] if rows else 0

	def typeahead(self, query, limit=6):
		if is_query_too_short(query) or not self.index_exists():
			return empty_typeahead()

		expanded_query, corrections = self._expand_query_with_corrections(query)
		hits = self.best_hits(self._prepare_fts_query(expanded_query))
		categories = [hit for hit in hits if hit["doctype"] == CATEGORY_DOCTYPE]
		products = [hit for hit in hits if hit["doctype"] != CATEGORY_DOCTYPE]
		return {
			"product_names": self.ranked_names(products, query)[:limit],
			"category_names": self.ranked_names(categories, query)[:limit],
			"corrected_words": {
				original: suggestion
				for original, suggestion in (corrections or {}).items()
				if original.lower() != suggestion.lower()
			},
		}

	def best_hits(self, fts_query):
		"""Each matching record once, as its best-ranked row, before any limit applies."""
		where, params = self.narrow_clause({}, None)
		columns = ", ".join(self.schema["metadata_fields"])
		try:
			# Bare columns come from the MIN(rank) row. The hidden `rank` is bm25.
			return self.sql(
				f"SELECT doc_id, title AS original_title, {columns}, MIN(rank) AS bm25_score "
				f"FROM search_fts WHERE search_fts MATCH ?{where} GROUP BY doc_id "
				"ORDER BY bm25_score LIMIT ?",
				(fts_query, *params, MAX_RERANK_CANDIDATES),
				read_only=True,
			)
		except sqlite3.Error as error:
			frappe.log_error(f"Search query failed: {error}")
			return []

	def ranked_names(self, hits, query):
		"""Names in core's rerank order. Typeahead ranks each doctype apart, so none crowds out another."""
		return [hit["name"] for hit in self._process_search_results(hits, query)]

	def facet_counts(self, filters):
		fts_query = self.fts_query_for((filters.get("search") or "").strip())
		if not fts_query:
			return empty_facets()
		return {**empty_facets(), **self.count_facets(fts_query, filters)}

	# -- spell correction -----------------------------------------------------------------------

	def _expand_query_with_corrections(self, query):
		"""Core's trigram correction plus an edit-distance fallback for short-word typos."""
		# Core's trigram threshold never fires for short terms ("shae"); memoized, one request expands twice.
		cache = getattr(self, "expanded_query_cache", None)
		if cache is None:
			cache = self.expanded_query_cache = {}
		if query not in cache:
			cache[query] = self.expand_query(query)
		return cache[query]

	def expand_query(self, query):
		"""Query with each unknown word swapped for its best vocabulary match, plus the corrections map."""
		expanded_terms = []
		corrections = {}

		for typed in query.strip().split():
			word = arabic_word_forms(typed)[0]
			if self.is_known_word(word):
				expanded_terms.append(word)
				continue

			similar_words = self._find_similar_words(word)
			if similar_words and similar_words[0] != word:
				expanded_terms.append(similar_words[0])
				corrections[typed] = similar_words[0]
				continue

			edit_distance_word = self.find_edit_distance_correction(word)
			if edit_distance_word and edit_distance_word != word.lower():
				expanded_terms.append(edit_distance_word)
				corrections[typed] = edit_distance_word
			else:
				expanded_terms.append(word)

		return " ".join(expanded_terms), corrections if corrections else None

	def is_known_word(self, word):
		"""In the vocabulary. An Arabic word also counts when one of its forms starts a vocabulary word."""
		if not is_arabic_query(word):
			return self.word_in_vocabulary(word)
		# Typeahead sends partial words: "الورد" must stay, not become a correction of "الوردة".
		return any(self.word_in_vocabulary(form, prefix=True) for form in arabic_word_forms(word))

	def word_in_vocabulary(self, word, prefix=False):
		word = word.lower()
		condition, params = "word = ?", (word,)
		if prefix:
			condition, params = "word >= ? AND word < ?", (word, word + LAST_CHARACTER)
		try:
			result = self.sql(
				f"SELECT 1 FROM search_vocabulary WHERE {condition} LIMIT 1", params, read_only=True
			)
			return bool(result)
		except sqlite3.Error:
			return False

	def fetch_trigram_candidates(self, word):
		"""Vocabulary words sharing at least one trigram with `word`."""
		word_trigrams = self._generate_trigrams(word)
		if not word_trigrams:
			return []

		placeholders = ",".join("?" * len(word_trigrams))
		try:
			return self.sql(
				f"""
				SELECT t.word, v.frequency, v.length, COUNT(*) as shared_trigrams
				FROM search_trigrams t
				JOIN search_vocabulary v ON t.word = v.word
				WHERE t.trigram IN ({placeholders})
					AND ABS(v.length - ?) <= ?
				GROUP BY t.word, v.frequency, v.length
				HAVING shared_trigrams >= 1
				ORDER BY shared_trigrams DESC, v.frequency DESC
			""",
				(*word_trigrams, len(word), MAX_EDIT_DISTANCE),
				read_only=True,
			)
		except sqlite3.Error:
			return []

	def find_edit_distance_correction(self, word):
		"""Best vocabulary correction for a genuine miss, ranked by Levenshtein distance."""
		word = word.lower()
		if len(word) < MIN_WORD_LENGTH:
			return None

		candidates = self.fetch_trigram_candidates(word)
		if not candidates:
			return None

		ranked = []
		for candidate_word, frequency, candidate_length, _shared_trigrams in candidates:
			if abs(candidate_length - len(word)) > MAX_EDIT_DISTANCE_FALLBACK:
				continue

			distance = levenshtein_distance(word, candidate_word)
			if distance > MAX_EDIT_DISTANCE_FALLBACK:
				continue

			sequence_ratio = difflib.SequenceMatcher(None, word, candidate_word).ratio()
			ranked.append((distance, -frequency, -sequence_ratio, candidate_word))

		if not ranked:
			return None

		ranked.sort()
		return ranked[0][3]


def market_rows(document: dict) -> list[dict]:
	"""The record's own row once per market, titled with that market's titles."""
	content = document.get("_own_content") or ""
	return [
		{
			**document,
			"doc_id": document["id"],
			"title": text,
			"content": searchable_content(text, content),
			"market": market,
		}
		for market, text in document.get("_market_titles", {}).items()
	]


def searchable_content(title: str | None, content: str) -> str:
	# The tokenizer has no Arabic rules: also index each Arabic word as a query normalises it.
	forms = arabic_search_forms(f"{title or ''} {content}")
	return f"{content} {forms}".strip()


def fts_phrase(word):
	"""A quoted FTS5 phrase. Long words match as a prefix, as in core."""
	escaped = word.replace('"', '""')
	return f'"{escaped}"*' if len(escaped) > MIN_WORD_LENGTH - 1 else f'"{escaped}"'


def levenshtein_distance(source, target):
	"""Levenshtein edit distance between two strings (iterative two-row DP)."""
	if source == target:
		return 0
	if not source:
		return len(target)
	if not target:
		return len(source)

	previous_row = list(range(len(target) + 1))
	for source_index, source_char in enumerate(source, start=1):
		current_row = [source_index]
		for target_index, target_char in enumerate(target, start=1):
			insert_cost = current_row[target_index - 1] + 1
			delete_cost = previous_row[target_index] + 1
			replace_cost = previous_row[target_index - 1] + (source_char != target_char)
			current_row.append(min(insert_cost, delete_cost, replace_cost))
		previous_row = current_row

	return previous_row[-1]
