import re
from functools import lru_cache
from urllib.parse import quote

import frappe
from erpnext.selling.doctype.customer.customer import (
	get_nested_links as _get_nested_links,
)
from frappe.geo.country_info import get_all
from frappe.query_builder import Case, DocType
from frappe.query_builder.functions import Count, Min, Sum
from frappe.utils import add_days, cint, create_batch, cstr, flt, get_datetime, now_datetime
from frappe.utils.data import strip_html
from pypika import Order

from commera.core import get_address_docs, get_party
from commera.order_access import get_key_access

# Ceiling for any IN (...) list this app sends to MariaDB/Postgres.
IN_CLAUSE_CHUNK_SIZE = 1000


def get_address_lines(address_display):
	"""ERPNext builds address_display as HTML; the dashboard renders plain text, so <br> tags leak."""
	if not address_display:
		return None

	lines = [
		strip_html(part).strip()
		for part in re.split(r"<br\s*/?>", cstr(address_display), flags=re.IGNORECASE)
	]
	return "\n".join(line for line in lines if line) or None


def validate_document_access(doctype: str, name: str | int, key: str | None = None):
	"""Return the document only if the session owns it, holds read permission on it, or holds its order key."""
	# Sales Order names are sequential, so every refusal must read the same: a "not found" or a
	# permission log would let a guest probing order numbers tell real orders from missing ones.
	if not frappe.db.exists(doctype, name):
		raise frappe.PermissionError
	document = frappe.get_doc(doctype, name)
	if document.owner == frappe.session.user:
		return document
	if doctype == "Sales Order" and get_key_access(document, key):
		return document
	if frappe.has_permission(doctype, "read", document):
		return document
	# has_permission logs its refusal even with throw off, and that log alone marks the order as real.
	frappe.clear_messages()
	raise frappe.PermissionError


def get_complete_nested_links(parent_group):
	"""Recursively fetch all nested item groups."""
	all_links = set()

	def recurse_node(group):
		children = get_nested_links("Item Group", group)
		for child in children:
			if child not in all_links:
				all_links.add(child)
				recurse_node(child)

	recurse_node(parent_group)
	return list(all_links)


def before_request():
	request_path = frappe.request.path

	if request_path.startswith("/en"):
		frappe.local.lang = "en"
	elif request_path.startswith("/ar"):
		frappe.local.lang = "ar"


def get_nested_links(link_doctype, link_name):
	"`get_nested_links` from erpnext, but with permissions ignored!"
	return _get_nested_links(link_doctype, link_name, ignore_permissions=True)


def get_product_list(filters=None, product_list=None, page=1, page_length=30, sort_by="default"):
	"""Storefront product grid: FTS-ranked when a rankable term is searched, frappe.qb otherwise."""
	from commera.search import query as search_query
	from commera.search.engine_cache import get_search_engine

	if product_list is not None or search_query.use_qb_fallback(filters):
		return get_product_list_qb(filters, product_list, page, page_length, sort_by)

	ranked_names = get_search_engine().search_products(filters, page, page_length, sort_by)
	if not ranked_names:
		return []

	# Hydrate through the qb select for one card shape, then restore rank: frappe.qb orders by name.
	cards_by_name = {
		card["name"]: card
		for card in get_product_list_qb(product_list=ranked_names, page_length=len(ranked_names))
	}
	return [cards_by_name[name] for name in ranked_names if name in cards_by_name]


def get_product_list_qb(filters=None, product_list=None, page=1, page_length=30, sort_by="default"):
	"""Retained frappe.qb product grid — browse, pinned lists, and the Arabic/short-term search fallback."""

	query = get_product_base_query(filters, product_list)
	style_attribute_variant = DocType("Style Attribute Variant")
	website_slideshow_item = DocType("Website Slideshow Item")
	color_size_item = DocType("Color Size Item")
	item_price_default = DocType("Item Price").as_("ip_default")
	item_price_sale = DocType("Item Price").as_("ip_sale")
	item = DocType("Item")
	has_custom_name_ar = frappe.db.has_column("Item", "custom_item_name_ar")

	discount_expr = (
		Case()
		.when(
			Min(item_price_default.price_list_rate) > 0,
			(
				(Min(item_price_default.price_list_rate) - Min(item_price_sale.price_list_rate))
				/ Min(item_price_default.price_list_rate)
			)
			* 100,
		)
		.else_(0)
	)
	query = (
		query.select(
			style_attribute_variant.name,
			style_attribute_variant.route,
			style_attribute_variant.item_style,
			style_attribute_variant.display_name,
			style_attribute_variant.attribute_value,
			style_attribute_variant.attribute_value.as_("color"),
			style_attribute_variant.item_group,
			style_attribute_variant.modified,
			style_attribute_variant.average_rating,
			style_attribute_variant.review_count,
			item.brand,
			item.item_name,
			item.is_stock_item,
			color_size_item.item_code.as_("variant_item_code"),
			Min(item_price_default.price_list_rate).as_("default_price"),
			Min(item_price_sale.price_list_rate).as_("sale_price"),
			website_slideshow_item.image.as_("image"),
			discount_expr.as_("discount_percent").as_("discount_percent"),
		)
		.groupby(style_attribute_variant.name)
		.limit(page_length)
		.offset((page - 1) * page_length)
	)
	if has_custom_name_ar:
		query = query.select(item.custom_item_name_ar)
	if sort_by == "price_low":
		query = query.orderby(Min(item_price_sale.price_list_rate), order=Order.asc)
	elif sort_by == "price_high":
		query = query.orderby(Min(item_price_sale.price_list_rate), order=Order.desc)
	elif sort_by == "name":
		query = query.orderby("display_name", order=Order.asc)
	elif sort_by == "new_arrival":
		query = query.orderby(style_attribute_variant.modified, order=Order.desc)
	elif sort_by == "discount":
		query = query.orderby(discount_expr, order=Order.desc)
	else:
		query = query.orderby("name", order=Order.asc)
	return shape_product_cards(query.run(as_dict=True))


def shape_product_cards(cards):
	"""Give every product card the one storefront card shape, whichever grid built it."""
	from commera.search.record_builder import sizes_for_variants
	from commera.search.sqlite_product_search import SqliteProductSearch

	if not cards:
		return cards

	unsized = [card["name"] for card in cards if card.get("sizes") is None]
	sizes_by_variant = sizes_for_variants(unsized) if unsized else {}

	for card in cards:
		if card.get("sizes") is None:
			card["sizes"] = sizes_by_variant.get(card["name"], [])
		for column in SqliteProductSearch.PRODUCT_DETAIL_COLUMNS:
			if column != "doc_id":
				card.setdefault(column, None)
		card.setdefault("average_rating", None)
		card.setdefault("review_count", None)
		# Mirrors record_builder.aggregate_prices so both grids agree on the price they filter and sort by.
		if card["effective_price"] is None:
			card["effective_price"] = (
				card["sale_price"] if card["sale_price"] is not None else (card["default_price"] or 0)
			)
		if card["has_discount"] is None:
			card["has_discount"] = 1 if flt(card["discount_percent"]) else 0
		# frappe.qb returns a datetime where the index holds a string, and the card is json.dumps'd into HTML.
		card["modified"] = cstr(card["modified"]) if card["modified"] else None
	return cards


def attach_live_prices(cards):
	"""Overlay the live Item Price onto index-hydrated cards."""
	# Item Price edits fire no Style Attribute Variant event, so the indexed price lags until the rebuild.
	from commera.search.record_builder import aggregate_prices, rates_by_item_code

	if not cards:
		return cards

	settings = frappe.get_cached_doc("Commera Settings")
	item_codes = list(
		{size["item_code"] for card in cards for size in (card.get("sizes") or []) if size.get("item_code")}
	)
	default_rate, sale_rate, sale_upto = rates_by_item_code(
		item_codes, settings.default_price_list, settings.sale_price_list
	)

	for card in cards:
		codes = [size["item_code"] for size in (card.get("sizes") or []) if size.get("item_code")]
		card.update(aggregate_prices(codes, default_rate, sale_rate, sale_upto))
	return cards


def get_total_product_count(filters=None, product_list=None):
	"""Total products for the grid's pagination controls — from SQLite unless frappe.qb owns the grid."""
	from commera.search import query as search_query
	from commera.search.engine_cache import get_search_engine

	if product_list is None and not search_query.use_qb_fallback(filters):
		return get_search_engine().search_count(filters)
	return get_product_count_qb(filters, product_list)


def get_product_count_qb(filters=None, product_list=None):
	"""Retained frappe.qb total count — used under the frappe.qb fallback and for pinned product lists."""

	query = get_product_base_query(filters, product_list)
	style_attribute_variant = DocType("Style Attribute Variant")
	query = query.select(Count(style_attribute_variant.name).distinct().as_("total_count"))
	result = query.run(as_dict=True)
	return result[0]["total_count"] if result else 0


def get_product_base_query(filters=None, product_list=None):
	commera_settings = frappe.get_cached_doc("Commera Settings")
	default_price_list = commera_settings.default_price_list
	sale_price_list = commera_settings.sale_price_list
	style_attribute_variant = DocType("Style Attribute Variant")
	website_slideshow_item = DocType("Website Slideshow Item")
	color_size_item = DocType("Color Size Item")
	item_price_default = DocType("Item Price").as_("ip_default")
	item_price_sale = DocType("Item Price").as_("ip_sale")
	item = DocType("Item")

	query = (
		frappe.qb.from_(style_attribute_variant)
		.left_join(website_slideshow_item)
		.on(
			(website_slideshow_item.parent == style_attribute_variant.name)
			& (website_slideshow_item.idx == 1)
		)
		.left_join(color_size_item)
		.on(color_size_item.parent == style_attribute_variant.name)
		.left_join(item_price_default)
		.on(
			(item_price_default.item_code == color_size_item.item_code)
			& (item_price_default.price_list == default_price_list)
		)
		.left_join(item_price_sale)
		.on(
			(item_price_sale.item_code == color_size_item.item_code)
			& (item_price_sale.price_list == sale_price_list)
		)
		.left_join(item)
		.on(item.name == style_attribute_variant.item_style)
	)
	if product_list:
		query = query.where(style_attribute_variant.name.isin(product_list))
	else:
		query = query.where(style_attribute_variant.is_published == 1)

	if filters:
		if filters.get("has_discount"):
			query = query.where(item_price_default.price_list_rate > item_price_sale.price_list_rate)
		if filters.get("subcategory"):
			query = query.where(style_attribute_variant.item_group.isin(filters["subcategory"]))
		if filters.get("colors"):
			query = query.where(style_attribute_variant.attribute_value.isin(filters["colors"]))
		if filters.get("sizes"):
			query = query.where(color_size_item.size.isin(filters["sizes"]))
		if filters.get("brands"):
			query = query.where(item.brand.isin(filters["brands"]))
		if filters.get("min_price"):
			query = query.where(item_price_sale.price_list_rate >= filters["min_price"])
		if filters.get("max_price"):
			query = query.where(item_price_sale.price_list_rate <= filters["max_price"])
		if filters.get("search"):
			search = filters.get("search")
			child_categories = get_complete_nested_links(search)
			search_condition = (
				(style_attribute_variant.display_name.like(f"%{search}%"))
				| (style_attribute_variant.attribute_value.like(f"%{search}%"))
				| (style_attribute_variant.name.like(f"%{search}%"))
				| (item.brand.like(f"%{search}%"))
				| (style_attribute_variant.display_name.like(f"%{search}%"))
				| (style_attribute_variant.item_group.like(f"%{search}%"))
				| (item.name.like(f"%{search}%"))
			)
			if child_categories:
				search_condition |= style_attribute_variant.item_group.isin(child_categories)

			if search.lower().startswith("men"):
				exclusion_condition = (~style_attribute_variant.display_name.like("%women%")) & (
					~style_attribute_variant.item_group.like("%women%")
				)
				search_condition = search_condition & exclusion_condition

			query = query.where(search_condition)
	return query


def get_delivery_configuration():
	shoe_arena_settings = frappe.get_cached_doc("Commera Settings")
	if not shoe_arena_settings.shipping_rule:
		return 0, 0
	shipping_rule = frappe.get_cached_doc("Shipping Rule", shoe_arena_settings.shipping_rule)
	if not shipping_rule or not shipping_rule.conditions:
		return 0, 0
	free_condition = next(
		(condition for condition in shipping_rule.conditions if condition.free_shipping), None
	)
	if not free_condition:
		condition = shipping_rule.conditions[0]
		return condition.shipping_amount, condition.to_value
	charge = next(
		(condition.shipping_amount for condition in shipping_rule.conditions if not condition.free_shipping),
		0,
	)
	return charge, free_condition.from_value


# The leading space is historical and live orders carry it: strip before comparing, never remove it.
COD_CHARGE_DESCRIPTION = " Cash on Delivery Charges"


def get_cod_configuration():
	shoe_arena_settings = frappe.get_cached_doc("Commera Settings")
	return (
		shoe_arena_settings.cod_charge_applicable_below,
		shoe_arena_settings.cod_charge,
	)


def format_theme_css():
	# jinja's safe globals return documents as plain dicts, so controller methods are unreachable from templates
	return frappe.get_cached_doc("Commera Settings", "Commera Settings").generate_theme_css()


def get_currency_symbol():
	currency = frappe.get_cached_value("Global Defaults", "Global Defaults", "default_currency")
	# Riyal has no glyph in the fonts the themes ship, so SAR alone borrows the icon font.
	if currency == "SAR":
		return '<span class="saudi-currency-symbol pe-0.5"></span>'
	return frappe.get_cached_value("Currency", currency, "symbol")


def get_addresses(party=None, address_type="Billing"):
	if not party:
		party = get_party()
	addresses = get_address_docs(party=party)
	return format_addresses(addresses, address_type)


def format_addresses(addresses, address_type):
	return [
		{
			"name": address.name,
			"title": address.address_title,
			"display": ", ".join(
				[
					part
					for part in [
						address.get("address_line1", ""),
						address.get("address_line2", ""),
						address.get("city", ""),
						address.get("state", ""),
						address.get("country", ""),
						address.get("pincode", ""),
						f"Phone: {address.get('phone')}" if address.get("phone") else "",
					]
					if part
				]
			),
		}
		for address in addresses
		if address.address_type == address_type
	]


PICKUP_ADDRESS_FIELDS = (
	"address_title",
	"address_line1",
	"address_line2",
	"city",
	"state",
	"pincode",
	"country",
	"phone",
	"custom_store_location",
)


def get_pickup_warehouses() -> list[str]:
	return frappe.get_all(
		"Warehouse",
		filters={"custom_store_pickup": 1, "disabled": 0, "is_group": 0},
		pluck="name",
	)


def get_pickup_addresses(warehouses: list[str]) -> dict:
	"""The Shop address shoppers are sent to, per warehouse. Desk can link more than one; the most
	recently changed wins, so the dashboard edits the same address checkout shows."""
	if not warehouses:
		return {}

	links = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": "Warehouse", "link_name": ["in", warehouses], "parenttype": "Address"},
		fields=["parent", "link_name"],
	)
	if not links:
		return {}

	warehouses_by_address = {}
	for link in links:
		warehouses_by_address.setdefault(link.parent, []).append(link.link_name)

	addresses = frappe.get_all(
		"Address",
		filters={"name": ["in", list(warehouses_by_address)], "address_type": "Shop", "disabled": 0},
		fields=["name", "address_type", *PICKUP_ADDRESS_FIELDS],
		order_by="modified desc",
	)

	pickup_addresses = {}
	for address in addresses:
		for warehouse in warehouses_by_address[address.name]:
			pickup_addresses.setdefault(warehouse, address)
	return pickup_addresses


def get_location_point(geojson) -> tuple[float, float] | None:
	"""(latitude, longitude) of the first point a Geolocation field holds; GeoJSON stores it reversed."""
	if not geojson:
		return None

	try:
		features = frappe.parse_json(geojson).get("features") or []
	except (ValueError, AttributeError):
		return None

	for feature in features:
		geometry = feature.get("geometry") or {}
		coordinates = geometry.get("coordinates") or []
		if geometry.get("type") == "Point" and len(coordinates) == 2:
			longitude, latitude = coordinates
			return flt(latitude), flt(longitude)
	return None


def get_directions_url(geojson) -> str:
	point = get_location_point(geojson)
	if not point:
		return ""
	return f"https://www.google.com/maps/dir/?api=1&destination={point[0]},{point[1]}"


@lru_cache(maxsize=2)
def get_country_list():
	country_list = get_all()
	country_list = [
		{
			"name": country,
			"code": details.get("code", "code"),
			"isd": details.get("isd", "isd"),
		}
		for country, details in country_list.items()
	]

	return country_list


def set_item_group_displayname(doc, method):
	# ERPNext's setup wizard and its fixtures insert Item Groups without knowing about commera's
	# shopper-facing name, so fall back to the group name instead of refusing the insert.
	if not doc.get("custom_displayname"):
		doc.custom_displayname = doc.item_group_name or doc.name


def prevent_welcome_email(doc, method):
	if hasattr(doc, "send_welcome_email"):
		doc.send_welcome_email = 0
	add_roles(doc, method)


def add_roles(doc, method):
	# Todo remove the accounts_user permmission and figure out how to create pe for customer
	roles_to_add = ["Customer"]

	for role in roles_to_add:
		doc.append("roles", {"role": role})


def get_local_lang_url(path: str) -> str:
	if "/ar/" in path and frappe.local.lang == "en":
		return path.replace("/ar/", "/en/")

	if "/en/" in path and frappe.local.lang == "ar":
		return path.replace("/en/", "/ar/")

	return path


def get_login_url_for_current_page() -> str:
	"""Login link that lands the shopper back on the page that refused them, query string intact."""
	# The login page reads `redirect-to` off its own query string: unencoded, it truncates at the first `&`.
	request = getattr(frappe.local, "request", None)
	# werkzeug always appends the separator to full_path, even with nothing after it.
	return_to = request.full_path.removesuffix("?") if request else "/"
	return f"/login?redirect-to={quote(return_to, safe='')}"


MAX_STOREFRONT_PAGE = 100000


def get_current_page():
	return min(max(cint(frappe.form_dict.get("page")), 1), MAX_STOREFRONT_PAGE)


PAGE_SIZE_OPTIONS = (12, 24, 48)
DEFAULT_PAGE_SIZE = 24


def get_page_size():
	"""The shopper's own choice for this session, else the merchant default off Commera Settings."""
	page_size = cint(frappe.form_dict.get("page_size"))
	if page_size not in PAGE_SIZE_OPTIONS:
		# A Select holds its value as text, and an unset one reads back blank.
		page_size = cint(frappe.db.get_single_value("Commera Settings", "products_per_page"))
	# Anything off the dropdown is someone editing the URL, and an unbounded page_length is a table scan.
	return page_size if page_size in PAGE_SIZE_OPTIONS else DEFAULT_PAGE_SIZE


def can_return(order_name, return_period_days):
	"""Check if the order is still within the return period."""

	delivered_on = [
		line.creation for line in get_delivery_note_lines(order_name, docstatus=1) if not line.is_return
	]
	if not delivered_on:
		return False
	return_deadline = add_days(get_datetime(max(delivered_on)), cint(return_period_days))
	return now_datetime() <= return_deadline


def get_available_stock(item_code, warehouse):
	return get_available_stocks([item_code], warehouse)[cstr(item_code)]


def get_available_stocks(item_codes, warehouse):
	"""Sellable qty per item code — two grouped queries for the whole list, not two per item."""
	if not warehouse:
		warehouse = "website_warehouse"
	if not item_codes:
		return {}

	item_codes = [cstr(item_code) for item_code in item_codes]
	bin_doctype = frappe.qb.DocType("Bin")
	bin_by_item_code = {}
	for item_code_chunk in create_batch(item_codes, IN_CLAUSE_CHUNK_SIZE):
		bin_rows = (
			frappe.qb.from_(bin_doctype)
			.select(bin_doctype.item_code, bin_doctype.actual_qty, bin_doctype.reserved_qty)
			.where((bin_doctype.item_code.isin(item_code_chunk)) & (bin_doctype.warehouse == warehouse))
		).run(as_dict=True)
		bin_by_item_code.update({cstr(row.item_code): row for row in bin_rows})

	pos_reserved_by_item_code = get_pos_reserved_qtys(item_codes, warehouse)

	stock_by_item_code = {}
	for item_code in item_codes:
		bin_data = bin_by_item_code.get(item_code)
		if not bin_data:
			stock_by_item_code[item_code] = {"stock_qty": 0, "in_stock": 0}
			continue
		actual_qty = (
			flt(bin_data.actual_qty)
			- flt(bin_data.reserved_qty)
			- flt(pos_reserved_by_item_code.get(item_code))
		)
		stock_by_item_code[item_code] = {"stock_qty": actual_qty, "in_stock": int(actual_qty > 0)}
	return stock_by_item_code


def get_discount_percent(default_price, sale_price):
	"""Calculate the discount percentage."""
	# A missing sale price is "not on sale", not "100% off" — only a real row may discount to zero.
	if not default_price or sale_price is None or sale_price >= default_price:
		return 0
	return ((default_price - sale_price) / default_price) * 100


def get_pos_reserved_qty(item_code, warehouse):
	return get_pos_reserved_qtys([item_code], warehouse).get(cstr(item_code), 0)


def get_pos_reserved_qtys(item_codes, warehouse):
	if not item_codes:
		return {}

	p_inv = frappe.qb.DocType("POS Invoice")
	p_item = frappe.qb.DocType("POS Invoice Item")

	reserved_by_item_code = {}
	for item_code_chunk in create_batch(list(item_codes), IN_CLAUSE_CHUNK_SIZE):
		rows = (
			frappe.qb.from_(p_inv)
			.from_(p_item)
			.select(p_item.item_code, Sum(p_item.stock_qty).as_("stock_qty"))
			.where(
				(p_inv.name == p_item.parent)
				& (p_inv.status.isin(["Paid", "Return"]))
				& (p_item.docstatus == 1)
				& (p_item.item_code.isin(item_code_chunk))
				& (p_item.warehouse == warehouse)
			)
			.groupby(p_item.item_code)
		).run(as_dict=True)
		reserved_by_item_code.update({cstr(row.item_code): flt(row.stock_qty) for row in rows})

	return reserved_by_item_code


def update_so_status_from_related_doc(doc, method):
	sales_orders = set()

	if doc.doctype == "Sales Order":
		frappe.enqueue(
			"commera.utils.update_sales_order_ecommerce_status",
			sales_order_name=doc.name,
			enqueue_after_commit=True,
		)

	elif doc.doctype == "Sales Invoice":
		sales_orders.update([d.sales_order for d in doc.items if d.sales_order])

	elif doc.doctype == "Delivery Note":
		sales_orders.update([d.against_sales_order for d in doc.items if d.against_sales_order])

	elif doc.doctype == "Shipping Request":
		if doc.ref_doctype == "Sales Order" and doc.ref_docname:
			sales_orders.add(doc.ref_docname)
		elif doc.delivery_note:
			sales_orders.update(
				frappe.get_all(
					"Delivery Note Item",
					filters={"parent": doc.delivery_note, "against_sales_order": ["is", "set"]},
					pluck="against_sales_order",
				)
			)
	for so in sales_orders:
		frappe.enqueue(
			"commera.utils.update_sales_order_ecommerce_status",
			sales_order_name=so,
			enqueue_after_commit=True,
		)


SHIPMENT_STATUS_LADDER = {
	"Draft": "Preparing for Shipment",
	"Ready To Ship": "Preparing for Shipment",
	"Pickup Scheduled": "Shipped",
	"In Transit": "Shipped",
	"Out For Delivery": "Shipped",
	"Undelivered": "Shipped",
	"Lost": "Shipped",
	"Delivered": "Delivered",
	"RTO": "Returned",
}


def update_sales_order_ecommerce_status(sales_order_name):
	docstatus = frappe.db.get_value("Sales Order", sales_order_name, "docstatus")

	if docstatus == 2:
		new_status = "Cancelled"
	elif docstatus == 0:
		new_status = "Waiting for Approval"
	else:
		new_status = get_fulfilment_status(sales_order_name)

	frappe.db.set_value("Sales Order", sales_order_name, "custom_ecommerce_status", new_status)


def get_fulfilment_status(sales_order_name) -> str:
	delivery_lines = get_delivery_note_lines(sales_order_name)
	submitted_lines = [line for line in delivery_lines if line.docstatus == 1]
	delivered_qty = sum(flt(line.qty) for line in submitted_lines if not line.is_return)
	returned_qty = abs(sum(flt(line.qty) for line in submitted_lines if line.is_return))

	if delivered_qty and returned_qty >= delivered_qty:
		return "Returned"
	if returned_qty:
		return "Partially Returned"

	if carrier_status := get_carrier_status(sales_order_name):
		return carrier_status

	if delivered_qty:
		return "Delivered"

	if any(line.docstatus == 0 and not line.is_return for line in delivery_lines):
		return "Preparing for Shipment"

	return "Order Received"


def get_carrier_status(sales_order_name) -> str | None:
	requests = frappe.get_all(
		"Shipping Request",
		filters={"ref_doctype": "Sales Order", "ref_docname": sales_order_name, "docstatus": ["<", 2]},
		fields=["status"],
		order_by="creation desc",
		limit=1,
	)
	if not requests:
		return None
	return SHIPMENT_STATUS_LADDER.get(cstr(requests[0].status))


def get_delivery_note_lines(sales_order_name, docstatus=None) -> list[dict]:
	delivery_note = DocType("Delivery Note")
	delivery_note_item = DocType("Delivery Note Item")
	query = (
		frappe.qb.from_(delivery_note_item)
		.join(delivery_note)
		.on(delivery_note.name == delivery_note_item.parent)
		.select(
			delivery_note.name,
			delivery_note.docstatus,
			delivery_note.is_return,
			delivery_note.creation,
			delivery_note_item.qty,
		)
		.where((delivery_note_item.against_sales_order == sales_order_name) & (delivery_note.docstatus < 2))
	)
	if docstatus is not None:
		query = query.where(delivery_note.docstatus == docstatus)
	return query.run(as_dict=True)


def get_first_option_photos(option_names: list) -> dict:
	"""The first gallery photo of each Style Attribute Variant, in gallery order."""
	first_photo_by_option = {}
	for chunk in create_batch(list(option_names), IN_CLAUSE_CHUNK_SIZE):
		for row in frappe.get_all(
			"Website Slideshow Item",
			filters={"parent": ["in", chunk], "parenttype": "Style Attribute Variant"},
			fields=["parent", "image"],
			order_by="idx asc",
		):
			first_photo_by_option.setdefault(row.parent, row.image)
	return first_photo_by_option


def get_item_images(item_codes: list) -> dict:
	"""Matches the option on the item's attribute value, not Color Size Item: a size taken off sale loses
	its row there but still sits on old orders."""
	if not item_codes:
		return {}

	items = frappe.get_all(
		"Item", filters={"name": ["in", item_codes]}, fields=["name", "image", "variant_of"]
	)
	template_by_item_code = {row.name: row.variant_of or row.name for row in items}
	templates = list(set(template_by_item_code.values()))
	options = read_product_options(templates)
	covers = pick_product_covers(templates, options)

	photo_by_option_key = {
		(option.template, option.attribute_name, option.attribute_value): option.photo
		for option in options
		if option.photo
	}
	option_photo_by_item_code = {}
	for row in frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", item_codes], "parenttype": "Item"},
		fields=["parent", "attribute", "attribute_value"],
	):
		photo = photo_by_option_key.get(
			(template_by_item_code.get(row.parent), row.attribute, row.attribute_value)
		)
		if photo:
			option_photo_by_item_code.setdefault(row.parent, photo)

	return {
		row.name: row.image
		or option_photo_by_item_code.get(row.name)
		or covers.get(template_by_item_code[row.name])
		for row in items
	}


def get_product_covers(templates: list) -> dict:
	"""A dashboard-created product never sets Item.image, so its cover is its earliest option's first photo."""
	if not templates:
		return {}
	return pick_product_covers(templates, read_product_options(templates))


def read_product_options(templates: list) -> list:
	configurators = frappe.get_all(
		"Style Attribute Configurator",
		filters={"item_template": ["in", templates]},
		fields=["name", "item_template"],
	)
	template_by_configurator = {row.name: row.item_template for row in configurators}
	if not template_by_configurator:
		return []

	options = frappe.get_all(
		"Style Attribute Variant",
		filters={"configurator": ["in", list(template_by_configurator)]},
		fields=["name", "configurator", "attribute_name", "attribute_value"],
		order_by="creation asc",
	)
	first_photo_by_option = get_first_option_photos([option.name for option in options])

	for option in options:
		option.template = template_by_configurator[option.configurator]
		option.photo = first_photo_by_option.get(option.name)
	return options


def pick_product_covers(templates: list, options: list) -> dict:
	image_by_template = dict(
		frappe.get_all("Item", filters={"name": ["in", templates]}, fields=["name", "image"], as_list=True)
	)
	covers = {}
	for template in templates:
		covers[template] = image_by_template.get(template) or next(
			(option.photo for option in options if option.template == template and option.photo), None
		)
	return covers
