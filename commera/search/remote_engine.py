"""What every engine on a search server shares. A subclass speaks one server's API; this class does the rest."""

import hashlib
import json
import re
from abc import abstractmethod

import frappe
from frappe.utils import create_batch, flt

from commera.product_detail import size_sort_key
from commera.search.engine import CARD_COLUMNS, SearchEngineBase, empty_facets, empty_typeahead
from commera.search.http_client import SearchServerError
from commera.search.record_builder import build_category_search_records, build_product_search_records

PRODUCT_DOCTYPE = "Style Attribute Variant"
CATEGORY_DOCTYPE = "Ecommerce Category"
REBUILD_TIMEOUT = 2 * 60 * 60
BATCH_SIZE = 250
# How long the site cache trusts a readiness answer. A ready index is trusted longer: only a rebuild or a
# settings change replaces it, and both refresh the answer.
READY_TTL = 60 * 60
NOT_READY_TTL = 60

# Facet name in FacetCounts -> (document field, the SearchFilters key that the facet must not narrow by).
FACETS = {
	"brand": ("brand", "brands"),
	"color": ("color", "colors"),
	"category": ("item_group", "subcategory"),
	"size": ("sizes", "sizes"),
}
LIST_FILTERS = {"subcategory": "item_group", "brands": "brand", "colors": "color", "sizes": "sizes"}
# sort_by -> (field, direction). Every engine breaks ties on `name`, so pages never overlap.
SORTS = {
	"price_low": ("effective_price", "asc"),
	"price_high": ("effective_price", "desc"),
	"name": ("display_name", "asc"),
	"new_arrival": ("modified", "desc"),
	"discount": ("discount_percent", "desc"),
}


class RemoteSearchEngine(SearchEngineBase):
	# The Search Engine option in Commera Settings, and the job that rebuilds this engine's indexes.
	NAME: str
	REBUILD_JOB: str

	def __init__(self, url=None, api_key=None, prefix=None):
		"""Connect with the given server details, or with those in Commera Settings."""
		settings = frappe.get_cached_doc("Commera Settings")
		self.client = self.make_client(url or settings.get("search_server_url"), api_key or get_api_key())
		prefix = prefix or settings.get("search_index_prefix") or frappe.local.site
		# Index names allow only [A-Za-z0-9_-] on every server; a site name carries dots.
		prefix = re.sub(r"[^A-Za-z0-9_-]", "_", prefix)
		self.products_uid = f"{prefix}_products"
		self.categories_uid = f"{prefix}_categories"

	# -- what a server's API must provide -------------------------------------------------------

	@classmethod
	@abstractmethod
	def make_client(cls, url, api_key): ...

	@classmethod
	@abstractmethod
	def check_connection(cls, url, api_key):
		"""Raise SearchServerError unless `url` answers and accepts `api_key`."""

	@abstractmethod
	def indexes_exist(self) -> bool: ...

	@abstractmethod
	def find_names(self, term, limit) -> tuple[list[str], list[str]]:
		"""The best product names and menu-entry names for `term`, in one round trip."""

	@abstractmethod
	def count_values(self, term, filters_by_field) -> list[dict[str, int]]:
		"""Value counts for each (field, clauses) pair, in one round trip."""

	@abstractmethod
	def find_page(self, term, clauses, page, page_length, sort) -> tuple[list[str], int]:
		"""One page of product names and the total match count. `sort` is a SORTS value or None."""

	@abstractmethod
	def count_matches(self, term, clauses) -> int: ...

	@abstractmethod
	def fetch_documents(self, names) -> list[dict]:
		"""The stored `card` and `size_items` of each named product, in any order."""

	@abstractmethod
	def upsert(self, uid, documents): ...

	@abstractmethod
	def delete(self, uid, ids): ...

	@abstractmethod
	def rebuild_one(self, uid, doctype, names):
		"""Index `names` into a new index for `uid`, then put it in place of the old one."""

	@abstractmethod
	def drop_indexes(self): ...

	# -- reads ----------------------------------------------------------------------------------

	def can_rank(self, term):
		return bool((term or "").strip()) and self.index_exists()

	def index_exists(self):
		"""Whether both indexes are ready, memoized for this instance and remembered in the site cache.

		Only a cache miss asks the server, so a normal page load makes no extra request.
		"""
		cached = getattr(self, "index_exists_cache", None)
		if cached is None:
			cached = self.read_readiness()
			self.index_exists_cache = cached
		return cached

	def read_readiness(self):
		if not self.client.url or self.client.is_down():
			return False
		ready = frappe.cache.get_value(self.ready_key)
		if ready is None:
			try:
				ready = self.indexes_exist()
			except SearchServerError as error:
				frappe.logger("commera.search").warning(str(error))
				ready = False
			self.remember_readiness(ready)
		return ready

	def mark_unavailable(self):
		self.index_exists_cache = False

	def remember_readiness(self, ready):
		frappe.cache.set_value(self.ready_key, ready, expires_in_sec=READY_TTL if ready else NOT_READY_TTL)
		self.index_exists_cache = ready

	@property
	def ready_key(self):
		return f"commera_search_ready:{self.NAME}:{self.client.url}:{self.products_uid}"

	def typeahead(self, query, limit=6):
		if not self.can_rank(query):
			return empty_typeahead()
		product_names, category_names = self.find_names(query.strip(), limit)
		return {"product_names": product_names, "category_names": category_names, "corrected_words": {}}

	def facet_counts(self, filters):
		term = (filters.get("search") or "").strip()
		if not self.can_rank(term):
			return empty_facets()
		# One query per facet, each without its own filter: a shopper must be able to widen a selection.
		counts = self.count_values(
			term, [(field, filter_clauses(filters, drop_key)) for field, drop_key in FACETS.values()]
		)
		facets = dict(zip(FACETS, counts, strict=True))
		facets["size"] = dict(sorted(facets["size"].items(), key=lambda item: size_sort_key(item[0])))
		return facets

	def search_products(self, filters, page=1, page_length=30, sort_by="default"):
		term, clauses = grid_terms(filters)
		if not self.can_rank(term):
			return []
		names, total = self.find_page(term, clauses, page, page_length, SORTS.get(sort_by))
		# The listing asks for the count next; the grid answer already holds it.
		self.total_hits = (query_key(term, clauses), total)
		return names

	def search_count(self, filters):
		term, clauses = grid_terms(filters)
		if not self.can_rank(term):
			return 0
		key, total = getattr(self, "total_hits", (None, 0))
		if key == query_key(term, clauses):
			return total
		return self.count_matches(term, clauses)

	def hydrate_cards(self, names):
		card_by_name = {}
		for chunk in create_batch(list(names), BATCH_SIZE):
			for document in self.fetch_documents(chunk):
				# A server may drop a null field when it updates a document, so restore the missing keys.
				card = {**dict.fromkeys(CARD_COLUMNS), **document["card"], "sizes": document["size_items"]}
				card_by_name[card["name"]] = card
		return [card_by_name[name] for name in names if name in card_by_name]

	# -- writes ---------------------------------------------------------------------------------

	def index_doc(self, doctype, docname):
		self.index_docs(doctype, [docname])

	def index_docs(self, doctype, names):
		names = list(names)
		uid, documents = self.documents_for(doctype, names)
		if documents:
			self.upsert(uid, documents)
		indexed = {document["name"] for document in documents}
		if missing := [name for name in names if name not in indexed]:
			self.delete(uid, [document_id(name) for name in missing])

	def remove_doc(self, doctype, docname):
		self.delete(self.uid_for(doctype), [document_id(docname)])

	def uid_for(self, doctype):
		return self.products_uid if doctype == PRODUCT_DOCTYPE else self.categories_uid

	def documents_for(self, doctype, names):
		"""The target index and its documents for `names`; a name that no longer qualifies yields none."""
		if doctype == PRODUCT_DOCTYPE:
			return self.products_uid, [
				product_document(record) for record in build_product_search_records(names)
			]
		return self.categories_uid, [
			category_document(record) for record in build_category_search_records(names)
		]

	def enqueue_full_rebuild(self, deduplicate=False):
		return frappe.enqueue(
			self.REBUILD_JOB,
			queue="long",
			enqueue_after_commit=True,
			timeout=REBUILD_TIMEOUT,
			job_id=self.REBUILD_JOB if deduplicate else None,
			deduplicate=deduplicate,
		)

	def ensure_index_built(self):
		if not self.client.url or self.index_exists():
			return None
		if not frappe.db.exists(PRODUCT_DOCTYPE, {"is_published": 1}):
			return None
		return self.enqueue_full_rebuild(deduplicate=True)

	def rebuild(self):
		"""Build both indexes beside the live ones, then swap them in, so search keeps serving meanwhile."""
		started = frappe.utils.now()
		for doctype, filters in ((PRODUCT_DOCTYPE, {"is_published": 1}), (CATEGORY_DOCTYPE, {"enabled": 1})):
			names = frappe.get_all(doctype, filters=filters, pluck="name")
			self.rebuild_one(self.uid_for(doctype), doctype, names)
		self.remember_readiness(True)

		# Writes made during the build went to the old index, which the swap just dropped. Replay them.
		for doctype in (PRODUCT_DOCTYPE, CATEGORY_DOCTYPE):
			if changed := frappe.get_all(doctype, filters={"modified": (">=", started)}, pluck="name"):
				self.index_docs(doctype, changed)

	def drop_index(self):
		self.drop_indexes()
		frappe.cache.delete_value(self.ready_key)
		self.index_exists_cache = None


def get_api_key():
	return frappe.utils.password.get_decrypted_password(
		"Commera Settings", "Commera Settings", "search_server_api_key", raise_exception=False
	)


def grid_terms(filters):
	return (filters.get("search") or "").strip(), filter_clauses(filters, None)


def query_key(term, clauses):
	return json.dumps([term, clauses], sort_keys=True)


def filter_clauses(filters, drop_key):
	"""SearchFilters as (operator, field, value) clauses, leaving out `drop_key` for disjunctive facets.

	The operators are "in" (any of a list), ">=", "<=" and "=". Each engine writes them in its own syntax.
	"""
	clauses = []
	for key, field in LIST_FILTERS.items():
		if key != drop_key and filters.get(key):
			clauses.append(("in", field, [str(value) for value in filters[key]]))
	# The ?category= tab scope is no facet, so it is never dropped.
	if filters.get("category_item_groups"):
		clauses.append(("in", "item_group", [str(value) for value in filters["category_item_groups"]]))
	if min_price := flt(filters.get("min_price")):
		clauses.append((">=", "effective_price", min_price))
	if max_price := flt(filters.get("max_price")):
		clauses.append(("<=", "effective_price", max_price))
	if filters.get("has_discount"):
		clauses.append(("=", "has_discount", 1))
	return clauses


def product_document(record):
	sizes = record["sizes"]
	card = record["detail"]
	return {
		"id": document_id(record["name"]),
		"name": record["name"],
		"title": record["title"],
		"title_ar": card.get("custom_item_name_ar") or "",
		"content": record["content"],
		"item_group": record["item_group"],
		"brand": record["brand"],
		"color": record["color"],
		"sizes": [size["size"] for size in sizes if size.get("size")],
		"size_items": sizes,
		"display_name": card["display_name"],
		"modified": card["modified"] or "",
		"effective_price": flt(card.get("effective_price")),
		"discount_percent": flt(card.get("discount_percent")),
		"has_discount": 1 if card.get("has_discount") else 0,
		"card": card,
	}


def category_document(record):
	return {"id": document_id(record["name"]), **record}


def document_id(name):
	"""Search servers allow only [A-Za-z0-9_-] in ids, and doc names may hold spaces or slashes."""
	return hashlib.sha1(name.encode()).hexdigest()
