"""Meilisearch as a storefront search engine."""

import json

from frappe.utils import create_batch

from commera.search.meili_client import MeiliClient
from commera.search.remote_engine import (
	BATCH_SIZE,
	PRODUCT_DOCTYPE,
	REBUILD_TIMEOUT,
	RemoteSearchEngine,
)

PRODUCT_SETTINGS = {
	"searchableAttributes": ["title", "title_ar", "content"],
	"filterableAttributes": [
		"name",
		"item_group",
		"brand",
		"color",
		"sizes",
		"effective_price",
		"has_discount",
	],
	"sortableAttributes": ["name", "display_name", "effective_price", "modified", "discount_percent"],
	# "sort" first: an explicit sort orders the whole grid, as ORDER BY does on SQLite, not just ties.
	"rankingRules": ["sort", "words", "typo", "proximity", "attribute", "exactness"],
	"pagination": {"maxTotalHits": 100000},
	"faceting": {"maxValuesPerFacet": 1000},
}
CATEGORY_SETTINGS = {"searchableAttributes": ["title", "content"], "filterableAttributes": ["name"]}
# Every word must match, as on SQLite. Meilisearch's default drops trailing words until something
# matches, so "premium black" would list every premium product and the counts would disagree.
MATCHING_STRATEGY = "all"


class MeilisearchEngine(RemoteSearchEngine):
	NAME = "Meilisearch"
	REBUILD_JOB = "commera.search.meili_search.rebuild_index"

	@classmethod
	def make_client(cls, url, api_key):
		return MeiliClient(url, api_key)

	@classmethod
	def check_connection(cls, url, api_key):
		MeiliClient(url, api_key).get("/indexes", limit=1)

	def indexes_exist(self):
		return all(self.client.get(f"/indexes/{uid}") for uid in (self.products_uid, self.categories_uid))

	# -- reads ----------------------------------------------------------------------------------

	def find_names(self, term, limit):
		queries = [
			text_query(term, indexUid=uid, limit=limit, attributesToRetrieve=["name"])
			for uid in (self.products_uid, self.categories_uid)
		]
		products, categories = self.multi_search(queries)
		return [hit["name"] for hit in products["hits"]], [hit["name"] for hit in categories["hits"]]

	def count_values(self, term, filters_by_field):
		queries = [
			text_query(term, clauses, indexUid=self.products_uid, limit=0, facets=[field])
			for field, clauses in filters_by_field
		]
		results = self.multi_search(queries)
		return [
			(result.get("facetDistribution") or {}).get(field) or {}
			for (field, _clauses), result in zip(filters_by_field, results, strict=True)
		]

	def find_page(self, term, clauses, page, page_length, sort):
		body = text_query(term, clauses, page=page, hitsPerPage=page_length, attributesToRetrieve=["name"])
		if sort:
			body["sort"] = [f"{sort[0]}:{sort[1]}", "name:asc"]
		result = self.client.post(self.search_path, body)
		return [hit["name"] for hit in result["hits"]], result["totalHits"]

	def count_matches(self, term, clauses):
		return self.client.post(self.search_path, text_query(term, clauses, page=1, hitsPerPage=0))[
			"totalHits"
		]

	def fetch_documents(self, names):
		return self.client.post(
			f"/indexes/{self.products_uid}/documents/fetch",
			{"filter": f"name IN {quote_list(names)}", "limit": len(names), "fields": ["card", "size_items"]},
		)["results"]

	def multi_search(self, queries):
		return self.client.post("/multi-search", {"queries": queries})["results"]

	@property
	def search_path(self):
		return f"/indexes/{self.products_uid}/search"

	# -- writes ---------------------------------------------------------------------------------

	def upsert(self, uid, documents):
		self.client.post(f"/indexes/{uid}/documents", documents)

	def delete(self, uid, ids):
		self.client.post(f"/indexes/{uid}/documents/delete-batch", ids)

	def rebuild_one(self, uid, doctype, names):
		temp_uid = f"{uid}_rebuild"
		client = self.client
		if client.get(f"/indexes/{temp_uid}"):
			client.wait_for_task(client.delete(f"/indexes/{temp_uid}"))
		client.wait_for_task(client.post("/indexes", {"uid": temp_uid, "primaryKey": "id"}))
		settings = PRODUCT_SETTINGS if doctype == PRODUCT_DOCTYPE else CATEGORY_SETTINGS
		client.wait_for_task(client.patch(f"/indexes/{temp_uid}/settings", settings))

		tasks = []
		for chunk in create_batch(names, BATCH_SIZE):
			_uid, documents = self.documents_for(doctype, chunk)
			if documents:
				tasks.append(client.post(f"/indexes/{temp_uid}/documents", documents))
		for task in tasks:
			client.wait_for_task(task, timeout=REBUILD_TIMEOUT)

		if not client.get(f"/indexes/{uid}"):
			client.wait_for_task(client.post("/indexes", {"uid": uid, "primaryKey": "id"}))
		client.wait_for_task(client.post("/swap-indexes", [{"indexes": [uid, temp_uid]}]))
		client.wait_for_task(client.delete(f"/indexes/{temp_uid}"))

	def drop_indexes(self):
		for uid in (self.products_uid, self.categories_uid):
			if self.client.get(f"/indexes/{uid}"):
				self.client.wait_for_task(self.client.delete(f"/indexes/{uid}"))


def rebuild_index():
	"""Background job: a full rebuild of the Meilisearch indexes."""
	MeilisearchEngine().rebuild()


def text_query(term, clauses=None, **params):
	query = {"q": term, "matchingStrategy": MATCHING_STRATEGY, **params}
	if clauses:
		query["filter"] = " AND ".join(render_clause(*clause) for clause in clauses)
	return query


def render_clause(operator, field, value):
	if operator == "in":
		return f"{field} IN {quote_list(value)}"
	return f"{field} {operator} {value}"


def quote_list(values):
	return f"[{', '.join(json.dumps(str(value)) for value in values)}]"
