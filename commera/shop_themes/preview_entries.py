# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, cstr

from commera.sdk import catalog

PREVIEW_ENTRY_PAGES = ("product", "products", "page", "search")
PAGE_SIZE = 20
MAX_SEARCH_LENGTH = 140


def list_entries(page, search=None, start=0):
	search = cstr(search).strip()
	start = max(cint(start), 0)
	if page == "product":
		return list_products(search, start, lambda product: product["handle"])
	if page == "search":
		entries = list_products(search, start, lambda product: product["title"])
		if search and not start:
			entries["entries"].insert(0, search_term_entry(search))
		return entries
	if page == "products":
		return list_collections(search, start)
	if page == "page":
		return list_pages(search, start)
	return {"entries": [], "has_more": False}


def resolve_entry(page, entry=None):
	entry = cstr(entry).strip()
	if page == "product":
		product = catalog.get_product(entry) if entry else None
		if product:
			return {"value": product["handle"], "title": product["title"]}
		newest = newest_product()
		return newest and {"value": newest["handle"], "title": newest["title"]}
	if page == "search":
		if entry:
			return search_term_entry(entry[:MAX_SEARCH_LENGTH])
		newest = newest_product()
		return newest and search_term_entry(newest["title"])
	if page == "products":
		collection = catalog.get_collection(entry) if entry else None
		if collection:
			return {"value": collection["handle"], "title": collection["title"]}
		return all_products_entry()
	if page == "page":
		pages = get_published_pages(filters={"route": entry} if entry else None, limit=1)
		if not pages and entry:
			pages = get_published_pages(limit=1)
		return page_entry(pages[0]) if pages else None
	return None


def list_products(search, start, get_value):
	page_number = start // PAGE_SIZE + 1
	result = catalog.list_products(query=search, sort="new_arrival", page=page_number, page_size=PAGE_SIZE)
	return {
		"entries": [
			{"value": get_value(product), "title": product["title"], "image": product["image"]}
			for product in result["products"]
		],
		"has_more": page_number * PAGE_SIZE < result["total"],
	}


def newest_product():
	products = catalog.list_products(sort="new_arrival", page_size=1)["products"]
	return products[0] if products else None


def search_term_entry(term):
	return {"value": term, "title": _('Search for "{0}"').format(term)}


def all_products_entry():
	return {"value": "", "title": _("All products")}


def list_collections(search, start):
	collections = [
		collection
		for collection in catalog.list_collections()
		if search.casefold() in collection["title"].casefold()
	]
	entries = [
		{"value": collection["handle"], "title": collection["title"], "image": collection["image"]}
		for collection in collections
	]
	if not search:
		entries.insert(0, all_products_entry())
	return {"entries": entries[start : start + PAGE_SIZE], "has_more": start + PAGE_SIZE < len(entries)}


def list_pages(search, start):
	pages = get_published_pages(
		filters={"name": ["like", f"%{search}%"]} if search else None, start=start, limit=PAGE_SIZE + 1
	)
	return {"entries": [page_entry(page) for page in pages[:PAGE_SIZE]], "has_more": len(pages) > PAGE_SIZE}


def get_published_pages(filters=None, start=0, limit=1):
	return frappe.get_all(
		"Shop Web Page",
		filters={"published": 1, "route": ["is", "set"], **(filters or {})},
		fields=["name", "route"],
		order_by="modified desc",
		limit_start=start,
		limit_page_length=limit,
	)


def page_entry(page):
	return {"value": page.route, "title": page.name}
