from math import ceil
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils.data import cint, cstr

from commera.builder_themes.cards import get_cards
from commera.localization.urls import url
from commera.sdk import catalog

PAGE_SIZE = 24
# Facet key and query parameter, in the order a filter sidebar lists them.
FILTER_KEYS = ("colors", "sizes", "brands")


def get_filter_labels() -> dict[str, str]:
	return {"colors": _("Colour"), "sizes": _("Size"), "brands": _("Brand")}


def get_sort_options(is_search: bool) -> tuple:
	options = (
		("new_arrival", _("Newest")),
		("price_low", _("Price, low to high")),
		("price_high", _("Price, high to low")),
		("discount", _("Biggest discount")),
		("name", _("Name")),
	)
	return (("default", _("Relevance")), *options) if is_search else options


class Listing:
	"""The product listing as a Builder page binds it: the products, plus a finished URL for every filter,
	sort and page. It reads the same query parameters as the theme's own listing, so links stay shareable."""

	def __init__(self, form: dict):
		self.query = cstr(form.get("search")).strip()
		self.collection = catalog.get_collection(form.get("category")) if form.get("category") else None
		self.selected = {
			key: [value for value in cstr(form.get(key)).split(",") if value] for key in FILTER_KEYS
		}
		self.on_sale = form.get("has_discount") == "1"
		self.sort_options = get_sort_options(bool(self.query))
		sort = form.get("sort_by")
		self.sort = sort if sort in dict(self.sort_options) else self.sort_options[0][0]
		self.page = max(cint(form.get("page")), 1)

	def get_data(self) -> dict:
		listing = self.get_listing()
		return {
			"title": self.get_title(),
			"query": self.query,
			"total": listing["total"],
			"products": get_cards(listing["products"]),
			"collections": self.get_collection_links(),
			"filters": self.get_filters(listing["facets"]),
			"active_filters": self.get_active_filters(),
			"has_active_filters": bool(self.get_active_filters()),
			"clear_filters_url": self.get_url(colors=None, sizes=None, brands=None, has_discount=None),
			"sort_options": [
				{"label": label, "url": self.get_url(sort_by=key), "is_active": key == self.sort}
				for key, label in self.sort_options
			],
			"pagination": self.get_pagination(max(ceil(listing["total"] / PAGE_SIZE), 1)),
		}

	def get_listing(self) -> dict:
		arguments = {
			"brands": self.selected["brands"],
			"colors": self.selected["colors"],
			"sizes": self.selected["sizes"],
			"on_sale": self.on_sale,
			"sort": self.sort,
			"page": self.page,
			"page_size": PAGE_SIZE,
		}
		if self.query:
			return catalog.search(self.query, **arguments)
		return catalog.list_products(collection=self.collection_handle, **arguments)

	@property
	def collection_handle(self) -> str | None:
		return self.collection["handle"] if self.collection else None

	def get_title(self) -> str:
		if self.query:
			return _("Results for “{0}”").format(self.query)
		return self.collection["title"] if self.collection else _("All products")

	def get_collection_links(self) -> list[dict]:
		links = [
			{"title": _("All products"), "url": self.get_url(category=None), "is_active": not self.collection}
		]
		for collection in catalog.list_collections():
			links.append(
				{
					"title": collection["title"],
					"url": self.get_url(category=collection["handle"]),
					"is_active": collection["handle"] == self.collection_handle,
				}
			)
		return links

	def get_filters(self, facets: dict) -> list[dict]:
		labels = get_filter_labels()
		return [
			{
				"name": labels[key],
				"values": [self.get_filter_value(key, facet) for facet in facets.get(key, [])],
			}
			for key in FILTER_KEYS
			if facets.get(key)
		]

	def get_filter_value(self, key: str, facet: dict) -> dict:
		selected = self.selected[key]
		is_active = facet["value"] in selected
		values = (
			[value for value in selected if value != facet["value"]]
			if is_active
			else [*selected, facet["value"]]
		)
		return {
			"label": facet["value"],
			"count": facet["count"],
			"url": self.get_url(**{key: ",".join(values)}),
			"is_active": is_active,
		}

	def get_active_filters(self) -> list[dict]:
		chips = [
			{
				"label": value,
				"url": self.get_url(
					**{key: ",".join(other for other in self.selected[key] if other != value)}
				),
			}
			for key in FILTER_KEYS
			for value in self.selected[key]
		]
		if self.on_sale:
			chips.append({"label": _("On sale"), "url": self.get_url(has_discount=None)})
		return chips

	def get_pagination(self, last_page: int) -> dict:
		return {
			"page": self.page,
			"last_page": last_page,
			"has_previous": self.page > 1,
			"previous_url": self.get_url(page=self.page - 1) if self.page > 1 else "",
			"has_next": self.page < last_page,
			"next_url": self.get_url(page=self.page + 1) if self.page < last_page else "",
			"pages": [
				{"number": number, "url": self.get_url(page=number), "is_current": number == self.page}
				for number in range(1, last_page + 1)
			],
		}

	def get_url(self, **overrides) -> str:
		"""This listing's URL with some parameters changed; a filter change goes back to page one."""
		values = {
			"search": self.query,
			"category": self.collection_handle,
			**{key: ",".join(self.selected[key]) for key in FILTER_KEYS},
			"has_discount": "1" if self.on_sale else None,
			"sort_by": self.sort if self.sort != self.sort_options[0][0] else None,
			"page": None,
			**overrides,
		}
		if values["page"] == 1:
			values["page"] = None
		query_string = urlencode({key: value for key, value in values.items() if value not in (None, "")})
		path = url("/products")
		return f"{path}?{query_string}" if query_string else path
