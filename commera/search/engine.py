"""The storefront search contract. Callers talk to a SearchEngineBase; SqliteProductSearch is the default engine."""

from abc import ABC, abstractmethod
from typing import TypedDict

from frappe.search.sqlite_search import MIN_WORD_LENGTH

MIN_QUERY_LENGTH = MIN_WORD_LENGTH

# The storefront product card. Every engine's hydrate_cards() and the frappe.qb grid fill these keys.
CARD_COLUMNS = (
	"name",
	"route",
	"item_style",
	"display_name",
	"attribute_value",
	"brand",
	"is_stock_item",
	"item_name",
	"custom_item_name_ar",
	"variant_item_code",
	"image",
	"hover_image",
	"item_group",
	"color",
	"default_price",
	"sale_price",
	"effective_price",
	"discount_percent",
	"has_discount",
	"sale_end_date",
	"modified",
)


class SearchFilters(TypedDict, total=False):
	"""The listing filters (see www/products/list.get_selected_filters). Each facet list holds selected values."""

	search: str
	category: str
	subcategory: list[str]
	brands: list[str]
	colors: list[str]
	sizes: list[str]
	min_price: float
	max_price: float
	has_discount: bool


class SearchResult(TypedDict):
	"""Ranked names, per-facet value counts and spelling corrections for one query."""

	product_names: list[str]
	category_names: list[str]
	corrected_words: dict[str, str]
	facets: dict[str, dict[str, int]]
	duration_ms: float
	search_ms: float
	facet_ms: float


class SearchEngineBase(ABC):
	"""What the storefront needs from a search engine. Engines rank and filter; Commera owns prices and cards."""

	# -- reads ----------------------------------------------------------------------------------

	@abstractmethod
	def can_rank(self, term: str) -> bool:
		"""Whether this engine can serve `term`. When False, the frappe.qb grid serves the request."""

	@abstractmethod
	def search(self, query: str, limit: int = 20, facet_filters: SearchFilters | None = None) -> SearchResult:
		"""Typeahead hits plus sidebar facets. Each facet is narrowed by every other selected filter."""

	@abstractmethod
	def search_products(
		self, filters: SearchFilters, page: int = 1, page_length: int = 30, sort_by: str = "default"
	) -> list[str]:
		"""One page of variant names for a text search, in display order.

		`sort_by` is default (relevance), price_low, price_high, name, new_arrival or discount.
		"""

	@abstractmethod
	def search_count(self, filters: SearchFilters) -> int:
		"""Exact total for search_products(), for pagination."""

	@abstractmethod
	def hydrate_cards(self, names: list[str]) -> list[dict]:
		"""Card dicts with CARD_COLUMNS and `sizes`, in `names` order. Prices may be stale; callers overlay live ones."""

	@abstractmethod
	def index_exists(self) -> bool:
		"""Whether the index is built and ready to serve reads."""

	# -- writes ---------------------------------------------------------------------------------

	@abstractmethod
	def index_doc(self, doctype: str, docname: str) -> None:
		"""Re-index one doc, or remove it when it no longer qualifies."""

	@abstractmethod
	def index_docs(self, doctype: str, names: list[str]) -> None:
		"""Re-index many docs, removing those that no longer qualify."""

	@abstractmethod
	def remove_doc(self, doctype: str, docname: str) -> None:
		"""Drop one doc from the index."""

	@abstractmethod
	def enqueue_full_rebuild(self, deduplicate: bool = False):
		"""Enqueue a rebuild that keeps the live index serving until the new one is ready."""

	@abstractmethod
	def ensure_index_built(self):
		"""Enqueue a build when the index is missing or a build was interrupted. Otherwise do nothing."""


def empty_result() -> SearchResult:
	"""The search() shape with nothing matched — for too-short queries and missing indexes."""
	return {
		"product_names": [],
		"category_names": [],
		"corrected_words": {},
		"facets": {"brand": {}, "color": {}, "size": {}, "category": {}},
		"duration_ms": 0.0,
		"search_ms": 0.0,
		"facet_ms": 0.0,
	}


def is_query_too_short(query):
	return len((query or "").strip()) < MIN_QUERY_LENGTH
