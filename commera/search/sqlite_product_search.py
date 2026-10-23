import difflib
import os
import re
import sqlite3
import time
from typing import ClassVar

import frappe
from frappe.search.sqlite_search import MAX_EDIT_DISTANCE, MIN_WORD_LENGTH, SQLiteSearch
from frappe.utils import create_batch, flt

from commera.search.engine import (
	CARD_COLUMNS,
	MIN_QUERY_LENGTH,
	SearchEngineBase,
	empty_result,
	is_query_too_short,
)
from commera.search.record_builder import (
	build_category_search_records,
	build_product_search_records,
)

FACET_COLUMN_TO_KEY = {"brand": "brand", "color": "color", "item_group": "category"}

# SQLite caps bound parameters per statement (999 on older builds), so bulk deletes go out in chunks.
SQLITE_PARAM_CHUNK_SIZE = 500

# Ceiling for the edit-distance fallback below; beyond 2 edits the "correction" is a different word.
MAX_EDIT_DISTANCE_FALLBACK = 2

SEARCH_CLASS_PATH = "commera.search.sqlite_product_search.SqliteProductSearch"
CORE_BUILD_INDEX = "frappe.search.sqlite_search.build_index"
BUILD_TIMEOUT = 2 * 60 * 60 + 10 * 60

ARABIC_PATTERN = re.compile("[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


class SqliteProductSearch(SQLiteSearch, SearchEngineBase):
	INDEX_NAME = "commera_product_search.db"

	INDEX_SCHEMA: ClassVar = {
		"text_fields": ["title", "content"],
		"metadata_fields": ["item_group", "brand", "color", "route_slug", "effective_price", "has_discount"],
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
		return {}

	def can_rank(self, term):
		"""True for a term of at least MIN_QUERY_LENGTH that is not Arabic, once the index exists."""
		# The FTS tokenizer has no Arabic stemming, so an Arabic term goes back to frappe.qb.
		term = (term or "").strip()
		if len(term) < MIN_QUERY_LENGTH or is_arabic_query(term):
			return False
		return self.index_exists()

	# -- index shape ----------------------------------------------------------------------------

	def index_exists(self):
		"""Whether a current-shape index is present, memoized for this instance."""
		# Read paths share one request-scoped instance; write/build paths use fresh ones, so it never goes stale.
		cached = getattr(self, "index_exists_cache", None)
		if cached is None:
			cached = (
				super().index_exists()
				and self._table_exists("product_detail")
				and self.fts_has_columns(("effective_price", "has_discount"))
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

		columns = ",\n".join(self.product_detail_column_defs())
		cursor.execute(f"CREATE TABLE IF NOT EXISTS product_detail ({columns})")
		for column in (
			"effective_price",
			"modified",
			"discount_percent",
			"display_name",
			"item_group",
			"brand",
			"color",
		):
			cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_pd_{column} ON product_detail({column})")

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

	def enqueue_full_rebuild(self, deduplicate=False):
		"""Enqueue a full rebuild on the long queue. Returns the enqueue payload."""
		# Core builds into a temp DB and renames it over the live one, so the index keeps serving.
		return frappe.enqueue(
			CORE_BUILD_INDEX,
			queue="long",
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
			doc.brand = record.get("brand") or ""
			doc.color = record.get("color") or ""
			doc.item_group = record.get("item_group") or doc.get("item_group") or ""
			doc.route_slug = record.get("route_slug") or ""
			doc.sizes = record.get("sizes") or []
			doc.product_detail = record.get("detail")
			detail = record.get("detail") or {}
			doc.effective_price = detail.get("effective_price")
			doc.has_discount = detail.get("has_discount")

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
			document["content"] = getattr(doc, "search_content", document.get("content", ""))
			document["_sizes"] = getattr(doc, "sizes", None) or []
			document["_detail"] = getattr(doc, "product_detail", None)
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

		self._with_connection(index_siblings)

	def write_search_size(self, cursor, doc_id, sizes):
		cursor.execute("DELETE FROM search_size WHERE doc_id = ?", (doc_id,))
		rows = [(doc_id, size.get("size") or "", size.get("item_code") or "") for size in sizes]
		if rows:
			cursor.executemany("INSERT INTO search_size (doc_id, size, item_code) VALUES (?, ?, ?)", rows)

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

	def remove_docs(self, doctype, names):
		"""Drop many docs from the FTS table and both sibling tables."""
		self.raise_if_not_indexed()
		for chunk in create_batch(list(names), SQLITE_PARAM_CHUNK_SIZE):
			doc_ids = tuple(f"{doctype}:{name}" for name in chunk)
			placeholders = ", ".join("?" for _ in doc_ids)
			for table in ("search_fts", "search_size", "product_detail"):
				self.sql(f"DELETE FROM {table} WHERE doc_id IN ({placeholders})", doc_ids, commit=True)

	# -- card hydration -------------------------------------------------------------------------

	def hydrate_cards(self, names):
		"""Card dicts for the given variant names, in `names` order, from product_detail + search_size."""
		if not names:
			return []

		card_by_name = {}
		sizes_by_name = {}
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

		cards = []
		for name in names:
			card = card_by_name.get(name)
			if not card:
				continue
			card["sizes"] = sizes_by_name.get(name, [])
			cards.append(card)
		return cards

	# -- facets ---------------------------------------------------------------------------------

	NARROW_KEY_TO_COLUMN: ClassVar = {
		"subcategory": "item_group",
		"brands": "brand",
		"colors": "color",
	}

	COLUMN_TO_NARROW_KEY: ClassVar = {column: key for key, column in NARROW_KEY_TO_COLUMN.items()}

	def facet_counts(self, fts_query, filters=None):
		"""Sidebar counts per facet, each narrowed by every OTHER selected filter but not by its own."""
		# Must match the frappe.qb sidebar: www/products/list.py pops the facet's own key before querying.
		selected = filters or {}
		counts = {}
		for column, key in FACET_COLUMN_TO_KEY.items():
			narrow_sql, narrow_params = self.narrow_clause(selected, self.COLUMN_TO_NARROW_KEY[column])
			rows = self.sql(
				f"SELECT {column} AS value, COUNT(*) AS count FROM search_fts "
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
		clauses = []
		params = []
		for narrow_key, column in self.NARROW_KEY_TO_COLUMN.items():
			if narrow_key == drop_key:
				continue
			values = selected.get(narrow_key)
			if not values:
				continue
			placeholders = ", ".join("?" for _ in values)
			clauses.append(f" AND {prefix}{column} IN ({placeholders})")
			params.extend(values)
		if drop_key != "sizes" and selected.get("sizes"):
			placeholders = ", ".join("?" for _ in selected["sizes"])
			clauses.append(
				f" AND {prefix}doc_id IN (SELECT doc_id FROM search_size WHERE size IN ({placeholders}))"
			)
			params.extend(selected["sizes"])
		price_sql, price_params = self.price_discount_clause(selected, prefix)
		clauses.append(price_sql)
		params.extend(price_params)
		return "".join(clauses), params

	def price_discount_clause(self, filters, prefix=""):
		"""SQL fragment + params for the min_price/max_price/has_discount filters against the snapshot."""
		# flt() the bounds: FTS5 content columns have no type affinity, and SQLite sorts every REAL below TEXT.
		clauses = []
		params = []
		min_price = flt(filters.get("min_price"))
		max_price = flt(filters.get("max_price"))
		if min_price:
			clauses.append(f" AND {prefix}effective_price >= ?")
			params.append(min_price)
		if max_price:
			clauses.append(f" AND {prefix}effective_price <= ?")
			params.append(max_price)
		if filters.get("has_discount"):
			clauses.append(f" AND {prefix}has_discount = 1")
		return "".join(clauses), params

	# -- search grid ----------------------------------------------------------------------------

	def detail_order(self, sort_by, prefix=""):
		"""ORDER BY fragment over product_detail columns; `name` breaks ties so pages never overlap."""
		columns = {
			"price_low": f"{prefix}effective_price ASC",
			"price_high": f"{prefix}effective_price DESC",
			"name": f"{prefix}display_name ASC",
			"new_arrival": f"{prefix}modified DESC",
			"discount": f"{prefix}discount_percent DESC",
		}
		primary = columns.get(sort_by)
		return f"{primary}, {prefix}name ASC" if primary else f"{prefix}name ASC"

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
		order = "bm25(search_fts), product_detail.name ASC"
		if sort_by != "default":
			order = self.detail_order(sort_by, "product_detail.")
		offset = (page - 1) * page_length
		rows = self.sql(
			"SELECT product_detail.name AS name FROM search_fts "
			"JOIN product_detail ON product_detail.doc_id = search_fts.doc_id "
			f"WHERE search_fts MATCH ?{where} ORDER BY {order} LIMIT ? OFFSET ?",
			(fts_query, *params, page_length, offset),
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
			"SELECT COUNT(*) AS count FROM search_fts "
			"JOIN product_detail ON product_detail.doc_id = search_fts.doc_id "
			f"WHERE search_fts MATCH ?{where}",
			(fts_query, *params),
			read_only=True,
		)
		return rows[0]["count"] if rows else 0

	def search(self, query, limit=20, facet_filters=None):
		if is_query_too_short(query) or not self.index_exists():
			return empty_result()

		raw = super().search(query)

		product_names = []
		category_names = []
		for hit in raw["results"]:
			if hit.get("doctype") == "Ecommerce Category":
				category_names.append(hit["name"])
			else:
				product_names.append(hit["name"])

		search_ms = raw["summary"]["duration"] * 1000

		facet_start = time.time()
		facets = {"brand": {}, "color": {}, "size": {}, "category": {}}
		expanded_query, _corrections = self._expand_query_with_corrections(query)
		facets.update(self.facet_counts(self._prepare_fts_query(expanded_query), facet_filters))
		facet_ms = (time.time() - facet_start) * 1000

		raw_corrections = raw["summary"].get("corrected_words") or {}
		corrected_words = {
			original: suggestion
			for original, suggestion in raw_corrections.items()
			if original.lower() != suggestion.lower()
		}

		return {
			"product_names": product_names[:limit],
			"category_names": category_names[:limit],
			"corrected_words": corrected_words,
			"facets": facets,
			"duration_ms": search_ms + facet_ms,
			"search_ms": round(search_ms, 3),
			"facet_ms": round(facet_ms, 3),
		}

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

		for word in query.strip().split():
			if self.word_in_vocabulary(word):
				expanded_terms.append(word)
				continue

			similar_words = self._find_similar_words(word)
			if similar_words and similar_words[0] != word:
				expanded_terms.append(similar_words[0])
				corrections[word] = similar_words[0]
				continue

			edit_distance_word = self.find_edit_distance_correction(word)
			if edit_distance_word and edit_distance_word != word.lower():
				expanded_terms.append(edit_distance_word)
				corrections[word] = edit_distance_word
			else:
				expanded_terms.append(word)

		return " ".join(expanded_terms), corrections if corrections else None

	def word_in_vocabulary(self, word):
		try:
			result = self.sql(
				"SELECT 1 FROM search_vocabulary WHERE word = ? LIMIT 1",
				(word.lower(),),
				read_only=True,
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


def is_arabic_query(text):
	"""True if the text carries any Arabic-script character."""
	return bool(ARABIC_PATTERN.search(text or ""))
