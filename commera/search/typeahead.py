"""Search as you type. The REST API, the themes and Jinja all return this one shape."""

from typing import TypedDict

from frappe.utils import cint, cstr

from commera.search.engine_cache import get_search_engine
from commera.search.query import build_product_cards, read_or_fall_back
from commera.shop_data import get_storefront_menu

DEFAULT_LIMIT = 6
MAX_LIMIT = 20


class CategoryLink(TypedDict):
	name: str
	label: str
	url: str


class Typeahead(TypedDict):
	query: str
	# Storefront product cards with live prices, best match first.
	products: list[dict]
	# Menu entries whose names match, linked to their listing.
	categories: list[CategoryLink]
	# The query the engine searched for when it corrected a typo, else None. Use it for "Did you mean".
	corrected_query: str | None


def get_typeahead(query: str, limit: int = DEFAULT_LIMIT) -> Typeahead:
	query = cstr(query).strip()
	limit = max(1, min(cint(limit) or DEFAULT_LIMIT, MAX_LIMIT))
	result: Typeahead = {"query": query, "products": [], "categories": [], "corrected_query": None}
	if not query:
		return result

	if get_search_engine().can_rank(query):
		ranked = read_or_fall_back(lambda: rank(query, limit), lambda: None)
		if ranked is not None:
			return {"query": query, **ranked}

	# SQLite ranks no short or Arabic term, and a failing search server ranks nothing: list frappe.qb matches.
	from commera.utils import get_product_list

	result["products"] = get_product_list(filters={"search": query}, page_length=limit)
	return result


def rank(query, limit):
	hits = get_search_engine().typeahead(query, limit)
	return {
		"products": build_product_cards(hits["product_names"]),
		"categories": get_category_links(hits["category_names"]),
		"corrected_query": get_corrected_query(query, hits["corrected_words"]),
	}


def get_category_links(names: list[str]) -> list[CategoryLink]:
	nodes = {node["name"]: node for node in walk(get_storefront_menu())}
	links = []
	for name in names:
		node = nodes.get(name)
		# A heading with no item group, brand or URL links nowhere, so it is no suggestion.
		if node and node.get("href"):
			links.append({"name": name, "label": node["label"], "url": node["href"]})
	return links


def get_corrected_query(query: str, corrected_words: dict[str, str]) -> str | None:
	if not corrected_words:
		return None
	return " ".join(corrected_words.get(word, word) for word in query.split())


def walk(nodes):
	for node in nodes:
		yield node
		yield from walk(node["children"])
