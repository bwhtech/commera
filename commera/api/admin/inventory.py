# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder import Case, Order
from frappe.query_builder.functions import Coalesce, Count, Lower, NullIf
from frappe.utils import create_batch
from frappe.utils.data import cint, cstr, flt

from commera.utils import IN_CLAUSE_CHUNK_SIZE, get_first_option_photos

PAGE_LENGTH = 50
LOW_STOCK_THRESHOLD = 5


@frappe.whitelist()
@frappe.read_only()
def get_inventory(
	availability: str | None = None,
	search: str | None = None,
	start: int = 0,
	page_length: int = PAGE_LENGTH,
	include_images: bool = True,
	sort: bool = True,
):
	"""Every sellable size and what is left of it."""
	frappe.has_permission("Item", ptype="read", throw=True)

	warehouse = get_ecommerce_warehouse()
	csi = frappe.qb.DocType("Color Size Item")
	sav = frappe.qb.DocType("Style Attribute Variant")
	tpl = frappe.qb.DocType("Item").as_("tpl_item")
	var_item = frappe.qb.DocType("Item").as_("var_item")
	bin_dt = frappe.qb.DocType("Bin")
	needs_var_item = sort or availability == "low"

	product_expr = Coalesce(NullIf(tpl.item_name, ""), sav.item_style)
	low_level_expr = (
		Case().when(Coalesce(var_item.safety_stock, 0) > 0, var_item.safety_stock).else_(LOW_STOCK_THRESHOLD)
		if needs_var_item
		else frappe.qb.terms.ValueWrapper(LOW_STOCK_THRESHOLD)
	)
	stock_expr = Coalesce(bin_dt.actual_qty, 0) if warehouse else frappe.qb.terms.ValueWrapper(0)
	committed_expr = Coalesce(bin_dt.reserved_qty, 0) if warehouse else frappe.qb.terms.ValueWrapper(0)

	def build_base():
		q = (
			frappe.qb.from_(csi)
			.join(sav)
			.on(sav.name == csi.parent)
			.left_join(tpl)
			.on(tpl.name == sav.item_style)
			.where((csi.parenttype == "Style Attribute Variant") & (Coalesce(csi.item_code, "") != ""))
		)
		if needs_var_item:
			q = q.left_join(var_item).on(var_item.name == csi.item_code)
		if warehouse:
			q = q.left_join(bin_dt).on((bin_dt.item_code == csi.item_code) & (bin_dt.warehouse == warehouse))
		if availability == "out":
			q = q.where(stock_expr <= 0)
		elif availability == "low":
			q = q.where((stock_expr > 0) & (stock_expr <= low_level_expr))
		if search:
			needle = f"%{cstr(search).casefold()}%"
			q = q.where(Lower(product_expr).like(needle) | Lower(csi.item_code).like(needle))
		return q

	start = cint(start)
	page_length = cint(page_length) or PAGE_LENGTH

	page_query = build_base().select(
		csi.item_code,
		product_expr.as_("product"),
		sav.item_style.as_("product_name"),
		Coalesce(NullIf(sav.attribute_value, ""), sav.display_name).as_("option"),
		sav.name.as_("variant"),
		csi.size,
		stock_expr.as_("stock"),
		committed_expr.as_("committed"),
		sav.is_published,
		low_level_expr.as_("low_stock_level"),
	)
	if sort:
		page_query = page_query.orderby(stock_expr, order=Order.asc).orderby(product_expr, order=Order.asc)
	page_rows = page_query.limit(page_length).offset(start).run(as_dict=True)

	if start == 0 and len(page_rows) < page_length:
		total = len(page_rows)
	else:
		total = cint(build_base().select(Count("*")).run()[0][0])

	if not page_rows:
		return {"rows": [], "total": total, "low_stock_threshold": LOW_STOCK_THRESHOLD}

	# Only fetch first option photos for variants on this page (skipped for analytics reports).
	first_image_by_variant = (
		get_first_option_photos([row.variant for row in page_rows]) if include_images else {}
	)

	rows = []
	for row in page_rows:
		quantity = flt(row.stock)
		low_level = cint(row.low_stock_level) or LOW_STOCK_THRESHOLD
		rows.append(
			{
				"item_code": row.item_code,
				"product": row.product or row.product_name,
				"product_name": row.product_name,
				"option": row.option,
				"variant": row.variant,
				"size": row.size,
				"image": first_image_by_variant.get(row.variant),
				"stock": quantity,
				"committed": flt(row.committed),
				"is_published": bool(row.is_published),
				"low_stock_level": low_level,
				"availability": describe_availability(quantity, low_level),
			}
		)

	return {
		"rows": rows,
		"total": total,
		"low_stock_threshold": LOW_STOCK_THRESHOLD,
	}


def get_low_stock_levels(item_codes) -> dict:
	"""The level each size is judged low at: Item.safety_stock where catalog.set_restock_level set one, the
	store default otherwise. Chunked - every sellable size in the store goes into this IN (...)."""
	if not item_codes:
		return {}

	levels = {}
	for item_code_chunk in create_batch(list(item_codes), IN_CLAUSE_CHUNK_SIZE):
		for row in frappe.get_all(
			"Item", filters={"name": ["in", item_code_chunk]}, fields=["name", "safety_stock"]
		):
			levels[cstr(row.name)] = cint(row.safety_stock) or LOW_STOCK_THRESHOLD
	return levels


def describe_availability(quantity, low_level: int = LOW_STOCK_THRESHOLD):
	if quantity <= 0:
		return "Out of stock"
	if quantity <= low_level:
		return "Low"
	return "In stock"


def get_ecommerce_warehouse():
	return frappe.get_cached_value("Commera Settings", "Commera Settings", "ecommerce_warehouse")


@frappe.whitelist(methods=["POST"])
def receive_stock(received_quantities: dict | str, valuation_rates: dict | str | None = None):
	"""Take stock in across any mix of products in one receipt. A rate is optional per line: Style Attribute
	Variant.receive_stock() falls back to the item's own valuation where none is given."""
	received_quantities = frappe.parse_json(received_quantities)
	if not isinstance(received_quantities, dict):
		frappe.throw(_("received_quantities must map item codes to quantities"))

	valuation_rates = frappe.parse_json(valuation_rates) if valuation_rates else {}
	if not isinstance(valuation_rates, dict):
		frappe.throw(_("valuation_rates must map item codes to rates"))

	wanted = {
		cstr(code): flt(quantity) for code, quantity in received_quantities.items() if flt(quantity) > 0
	}
	if not wanted:
		frappe.throw(_("Enter a quantity for at least one item"))

	rows = frappe.get_all(
		"Color Size Item",
		filters={"item_code": ["in", list(wanted)], "parenttype": "Style Attribute Variant"},
		fields=["item_code", "parent"],
	)
	quantities_by_variant = {}
	rates_by_variant = {}
	for row in rows:
		item_code = cstr(row.item_code)
		quantities_by_variant.setdefault(row.parent, {})[item_code] = wanted[item_code]
		# A rate whose line carries no quantity is dropped along with it, so it can never
		# reach receive_stock() as a size the receipt does not hold.
		if item_code in valuation_rates:
			rates_by_variant.setdefault(row.parent, {})[item_code] = valuation_rates[item_code]

	unknown = sorted(set(wanted) - {cstr(row.item_code) for row in rows})
	if unknown:
		frappe.throw(_("Not a sellable size: {0}").format(", ".join(unknown)))

	stock_entries = []
	for variant_name, quantities in quantities_by_variant.items():
		variant = frappe.get_doc("Style Attribute Variant", variant_name)
		stock_entries.append(variant.receive_stock(quantities, rates_by_variant.get(variant_name)))

	return {"stock_entries": stock_entries}


# commera keeps no adjustment-with-reason ledger of its own, so get_stock_movements() below reads
# ERPNext's Stock Ledger Entry, scoped to the shop's own warehouse.
STOCK_ENTRY_REASON_LABELS = {
	"Material Receipt": "Received",
	"Material Issue": "Removed",
	"Material Transfer": "Transferred",
}
VOUCHER_TYPE_REASON_LABELS = {
	"Delivery Note": "Sold",
	"Sales Invoice": "Sold",
	"Stock Reconciliation": "Stock count",
	"Purchase Receipt": "Received",
}


@frappe.whitelist()
@frappe.read_only()
def get_stock_movements(start: int = 0, page_length: int = PAGE_LENGTH):
	"""Every stock movement against the shop's own warehouse, newest first. Read-only."""
	# Gated the same way get_inventory() is, on Item read - Stock Ledger Entry's own permission
	# is narrower than the role the dashboard runs under actually needs for this read.
	frappe.has_permission("Item", ptype="read", throw=True)

	warehouse = get_ecommerce_warehouse()
	if not warehouse:
		return {"rows": [], "total": 0}

	filters = {"warehouse": warehouse, "is_cancelled": 0}
	total = frappe.db.count("Stock Ledger Entry", filters)

	entries = frappe.get_all(
		"Stock Ledger Entry",
		filters=filters,
		fields=[
			"name",
			"posting_date",
			"posting_time",
			"item_code",
			"actual_qty",
			"voucher_type",
			"voucher_no",
			"owner",
		],
		order_by="posting_date desc, posting_time desc, creation desc",
		start=cint(start),
		page_length=cint(page_length) or PAGE_LENGTH,
	)
	if not entries:
		return {"rows": [], "total": total}

	item_codes = list({cstr(row.item_code) for row in entries})
	product_by_item_code = get_product_titles(item_codes)
	reason_by_voucher = get_movement_reasons(entries)
	full_name_by_user = get_user_full_names([row.owner for row in entries])

	rows = []
	for row in entries:
		item_code = cstr(row.item_code)
		rows.append(
			{
				"name": row.name,
				"date": row.posting_date,
				"sku": item_code,
				"product": product_by_item_code.get(item_code, item_code),
				"delta": flt(row.actual_qty),
				"reason": reason_by_voucher.get((row.voucher_type, row.voucher_no), row.voucher_type),
				"by": full_name_by_user.get(row.owner, row.owner),
			}
		)

	return {"rows": rows, "total": total}


def get_product_titles(item_codes):
	"""The parent product's title for a set of sizes - one batched hop through Color Size Item
	and Style Attribute Variant to Item.item_name, same join shape get_inventory() uses."""
	sizes = frappe.get_all(
		"Color Size Item",
		filters={"item_code": ["in", item_codes], "parenttype": "Style Attribute Variant"},
		fields=["item_code", "parent"],
	)
	if not sizes:
		return {}

	variants = frappe.get_all(
		"Style Attribute Variant",
		filters={"name": ["in", list({row.parent for row in sizes})]},
		fields=["name", "item_style"],
	)
	item_style_by_variant = {row.name: row.item_style for row in variants}

	item_styles = list({item_style for item_style in item_style_by_variant.values() if item_style})
	titles = (
		{
			row.name: row.item_name
			for row in frappe.get_all(
				"Item", filters={"name": ["in", item_styles]}, fields=["name", "item_name"]
			)
		}
		if item_styles
		else {}
	)

	product_by_item_code = {}
	for row in sizes:
		item_style = item_style_by_variant.get(row.parent)
		product_by_item_code[cstr(row.item_code)] = titles.get(item_style) or item_style
	return product_by_item_code


def get_movement_reasons(entries):
	"""A human reason per (voucher_type, voucher_no) - only Stock Entry needs a second lookup,
	to tell a receipt from an issue; every other voucher type reads off VOUCHER_TYPE_REASON_LABELS."""
	stock_entry_names = list({row.voucher_no for row in entries if row.voucher_type == "Stock Entry"})
	stock_entry_type_by_name = (
		{
			row.name: row.stock_entry_type
			for row in frappe.get_all(
				"Stock Entry",
				filters={"name": ["in", stock_entry_names]},
				fields=["name", "stock_entry_type"],
			)
		}
		if stock_entry_names
		else {}
	)

	reasons = {}
	for row in entries:
		key = (row.voucher_type, row.voucher_no)
		if row.voucher_type == "Stock Entry":
			stock_entry_type = stock_entry_type_by_name.get(row.voucher_no)
			reasons[key] = STOCK_ENTRY_REASON_LABELS.get(
				stock_entry_type, stock_entry_type or row.voucher_type
			)
		else:
			reasons[key] = VOUCHER_TYPE_REASON_LABELS.get(row.voucher_type, row.voucher_type)
	return reasons


def get_user_full_names(owners):
	names = list({owner for owner in owners if owner})
	if not names:
		return {}
	return {
		row.name: row.full_name
		for row in frappe.get_all("User", filters={"name": ["in", names]}, fields=["name", "full_name"])
	}
