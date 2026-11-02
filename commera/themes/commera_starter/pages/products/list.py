from math import ceil
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils.data import cint, cstr, flt

from commera import seo
from commera.sdk import catalog
from commera.sdk.format import money

PAGE_SIZE = 24
LIST_FILTERS = ("sizes", "colors", "brands")


def get_context(context):
	form = frappe.form_dict
	context.query = cstr(form.get("search")).strip()
	context.collection = catalog.get_collection(form.get("category")) if form.get("category") else None
	context.selected = get_selected_filters(form)
	context.sort_options = get_sort_options(bool(context.query))
	sort = (
		form.get("sort_by")
		if form.get("sort_by") in dict(context.sort_options)
		else context.sort_options[0][0]
	)
	context.selected.sort_by = sort

	arguments = {
		"brands": context.selected.brands,
		"colors": context.selected.colors,
		"sizes": context.selected.sizes,
		"min_price": context.selected.min,
		"max_price": context.selected.max,
		"on_sale": context.selected.has_discount,
		"sort": sort,
		"page": max(cint(form.get("page")), 1),
		"page_size": PAGE_SIZE,
	}
	if context.query:
		context.listing = catalog.search(context.query, **arguments)
	else:
		context.listing = catalog.list_products(
			collection=context.collection["handle"] if context.collection else None, **arguments
		)

	context.listing_layout = "search" if context.query else "products"
	context.last_page = ceil(context.listing["total"] / PAGE_SIZE)
	context.page_url = lambda page: get_listing_url(context, page=page)
	context.chips = get_chips(context)
	context.reset_url = get_listing_url(
		context, **dict.fromkeys((*LIST_FILTERS, "min", "max", "has_discount"))
	)
	add_seo(context)
	return context


def get_selected_filters(form):
	return frappe._dict(
		{key: [value for value in cstr(form.get(key)).split(",") if value] for key in LIST_FILTERS},
		min=flt(form.get("min")) if form.get("min") else None,
		max=flt(form.get("max")) if form.get("max") else None,
		has_discount=form.get("has_discount") == "1",
	)


def get_sort_options(is_search):
	options = [
		("new_arrival", _("Newest")),
		("price_low", _("Price, low to high")),
		("price_high", _("Price, high to low")),
		("discount", _("Biggest discount")),
		("name", _("Name")),
	]
	return [("default", _("Relevance")), *options] if is_search else options


def get_listing_url(context, **overrides):
	values = {
		"search": context.query,
		"category": context.collection["handle"] if context.collection else None,
		**{key: ",".join(context.selected[key]) for key in LIST_FILTERS},
		"min": context.selected.min,
		"max": context.selected.max,
		"has_discount": "1" if context.selected.has_discount else None,
		"sort_by": context.selected.sort_by
		if context.selected.sort_by != context.sort_options[0][0]
		else None,
		**overrides,
	}
	if values.get("page") == 1:
		values["page"] = None
	query_string = urlencode({key: value for key, value in values.items() if value not in (None, "")})
	path = f"/{frappe.local.lang or 'en'}/products"
	return f"{path}?{query_string}" if query_string else path


def get_chips(context):
	chips = [
		{
			"label": value,
			"url": get_listing_url(
				context, **{key: ",".join(other for other in context.selected[key] if other != value)}
			),
		}
		for key in LIST_FILTERS
		for value in context.selected[key]
	]
	if context.selected.min is not None or context.selected.max is not None:
		chips.append(
			{"label": get_price_label(context.selected), "url": get_listing_url(context, min=None, max=None)}
		)
	if context.selected.has_discount:
		chips.append({"label": _("On sale"), "url": get_listing_url(context, has_discount=None)})
	return chips


def get_price_label(selected):
	if selected.max is None:
		return _("From {0}").format(money(selected.min))
	if selected.min is None:
		return _("Up to {0}").format(money(selected.max))
	return _("{0} to {1}").format(money(selected.min), money(selected.max))


def add_seo(context):
	if context.query:
		context.seo = seo.build_page_seo({"noindex": 1}, display_name=_("Search: {0}").format(context.query))
		return

	title = context.collection["title"] if context.collection else ""
	breadcrumbs = [{"label": title or _("Products"), "href": ""}]
	context.seo = seo.build_collection_seo(title, breadcrumbs, total_count=context.listing["total"])
	context.json_ld = [
		seo.build_collection_json_ld(title, breadcrumbs, context.listing["total"]),
		seo.build_breadcrumb_json_ld(breadcrumbs),
	]
