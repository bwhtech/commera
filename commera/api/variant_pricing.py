# Copyright (c) 2025, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import create_batch
from frappe.utils.data import cint, cstr, flt

from commera.app_events import add_changed_products
from commera.utils import IN_CLAUSE_CHUNK_SIZE

PRODUCT_DOCTYPE = "Style Attribute Variant"

# Above this many inserts the request would outlive the gateway timeout, so it moves to a worker.
BACKGROUND_INSERT_THRESHOLD = 200

JOB_COMMIT_CHUNK_SIZE = 500


def get_selling_price_lists():
	settings = frappe.get_cached_doc("Commera Settings")
	if not settings.default_price_list or not settings.sale_price_list:
		frappe.throw(_("Set Default Price List and Sale Price List in Commera Settings first."))
	return settings.default_price_list, settings.sale_price_list


def get_base_price_rows_by_key(item_codes, price_lists):
	"""Base (no-customer) selling rows keyed (item_code, price_list) - customer rows are negotiated contracts."""
	if not item_codes:
		return {}

	price_rows = []
	for item_code_chunk in create_batch(list(item_codes), IN_CLAUSE_CHUNK_SIZE):
		price_rows.extend(
			frappe.get_all(
				"Item Price",
				filters={
					"item_code": ["in", item_code_chunk],
					"price_list": ["in", price_lists],
					"selling": 1,
					"customer": ["is", "not set"],
				},
				fields=["name", "item_code", "price_list", "price_list_rate"],
				order_by="creation asc",
			)
		)
	return {(cstr(price_row.item_code), price_row.price_list): price_row for price_row in price_rows}


def get_size_item_codes(item_template, style_attribute_variant_list=None):
	"""Every leaf size Item under this template, derived server-side so a forged variant name matches nothing."""
	style_attribute_variant = frappe.qb.DocType(PRODUCT_DOCTYPE)
	color_size_item = frappe.qb.DocType("Color Size Item")
	item = frappe.qb.DocType("Item")

	variant_name_chunks = (
		create_batch(list(style_attribute_variant_list), IN_CLAUSE_CHUNK_SIZE)
		if style_attribute_variant_list
		else [None]
	)

	found = []
	for variant_name_chunk in variant_name_chunks:
		query = (
			frappe.qb.from_(style_attribute_variant)
			.inner_join(color_size_item)
			.on(
				(color_size_item.parent == style_attribute_variant.name)
				& (color_size_item.parenttype == PRODUCT_DOCTYPE)
			)
			.inner_join(item)
			.on(item.name == color_size_item.item_code)
			.select(item.name)
			.distinct()
			.where((style_attribute_variant.item_style == item_template) & (item.variant_of == item_template))
		)
		if variant_name_chunk is not None:
			query = query.where(style_attribute_variant.name.isin(variant_name_chunk))
		# Item Price.item_code is Data, so an autoincrement-named Item returns an int and needs cstr to match.
		found.extend(cstr(row.name) for row in query.run(as_dict=True))

	return list(dict.fromkeys(found))


@frappe.whitelist(methods=["POST"])
def set_variant_prices(
	item_template: str,
	default_rate: float | str | None = None,
	sale_rate: float | str | None = None,
	overwrite_existing: int | str = 0,
	style_attribute_variant_list: list[str] | str | None = None,
) -> dict:
	"""Price every size Item under a template in one pass. A non-positive rate leaves that price list
	alone, and existing prices are untouched unless overwrite_existing is set."""
	frappe.has_permission("Item", doc=item_template, ptype="write", throw=True)
	frappe.has_permission("Item Price", ptype="create", throw=True)
	frappe.has_permission("Item Price", ptype="write", throw=True)

	if style_attribute_variant_list:
		style_attribute_variant_list = frappe.parse_json(style_attribute_variant_list)

	overwrite_existing = cint(overwrite_existing)
	default_price_list, sale_price_list = get_selling_price_lists()
	rate_by_price_list = {
		price_list: flt(rate)
		for price_list, rate in ((default_price_list, default_rate), (sale_price_list, sale_rate))
		if flt(rate) > 0
	}

	counts = {"created": 0, "updated": 0, "skipped": 0, "queued": 0}
	if not rate_by_price_list:
		return counts

	item_codes = get_size_item_codes(item_template, style_attribute_variant_list)
	if not item_codes:
		return counts

	existing_price_by_key = get_base_price_rows_by_key(item_codes, list(rate_by_price_list))

	price_rows_to_insert = []
	for price_list, rate in rate_by_price_list.items():
		stale_price_names = []
		for item_code in item_codes:
			existing_price = existing_price_by_key.get((item_code, price_list))
			if not existing_price:
				price_rows_to_insert.append(
					{"item_code": item_code, "price_list": price_list, "price_list_rate": rate}
				)
			elif overwrite_existing and flt(existing_price.price_list_rate) != rate:
				stale_price_names.append(existing_price.name)
			else:
				counts["skipped"] += 1

		counts["updated"] += set_item_price_rate(stale_price_names, rate)

	if counts["updated"]:
		add_changed_products([item_template], "price")

	if len(price_rows_to_insert) > BACKGROUND_INSERT_THRESHOLD:
		frappe.enqueue(
			"commera.api.variant_pricing.insert_item_prices_in_background",
			queue="long",
			timeout=1800,
			enqueue_after_commit=True,
			item_template=item_template,
			price_rows=price_rows_to_insert,
		)
		counts["queued"] = len(price_rows_to_insert)
	else:
		counts["created"] = insert_item_prices(price_rows_to_insert)

	add_pricing_comment(item_template, counts)
	return counts


def set_item_price_rate(price_names, rate):
	"""One set-based statement per chunk — the row count here is the whole catalogue on a big template."""
	if not price_names:
		return 0

	item_price = frappe.qb.DocType("Item Price")
	for price_name_chunk in create_batch(price_names, IN_CLAUSE_CHUNK_SIZE):
		frappe.qb.update(item_price).set(item_price.price_list_rate, rate).where(
			item_price.name.isin(price_name_chunk)
		).run()
	return len(price_names)


def insert_item_prices(price_rows, commit_in_chunks=False):
	"""Insert through the document API so ERPNext's own Item Price validation still runs."""
	if not price_rows:
		return 0

	stock_uom_by_item_code = get_stock_uoms({row["item_code"] for row in price_rows})
	created_count = 0
	for price_row_chunk in create_batch(price_rows, JOB_COMMIT_CHUNK_SIZE):
		for price_row in price_row_chunk:
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": price_row["item_code"],
					"price_list": price_row["price_list"],
					"price_list_rate": price_row["price_list_rate"],
					"selling": 1,
					# ERPNext keys its duplicate-price check on uom; blank makes every later edit look like a new price.
					"uom": stock_uom_by_item_code.get(price_row["item_code"]),
				}
			).insert()
			created_count += 1
		if commit_in_chunks:
			# nosemgrep: frappe-manual-commit  # job only — a mid-run crash keeps the chunks already priced
			frappe.db.commit()

	return created_count


def insert_item_prices_in_background(item_template, price_rows):
	created_count = insert_item_prices(price_rows, commit_in_chunks=True)
	add_pricing_comment(item_template, {"created": created_count, "updated": 0, "skipped": 0, "queued": 0})
	# nosemgrep: frappe-manual-commit  # job only — the worker's transaction is nobody else's to commit
	frappe.db.commit()


def get_stock_uoms(item_codes):
	stock_uom_by_item_code = {}
	for item_code_chunk in create_batch(list(item_codes), IN_CLAUSE_CHUNK_SIZE):
		for item_row in frappe.get_all(
			"Item", filters={"name": ["in", item_code_chunk]}, fields=["name", "stock_uom"]
		):
			stock_uom_by_item_code[cstr(item_row.name)] = item_row.stock_uom
	return stock_uom_by_item_code


def add_pricing_comment(item_template, counts):
	"""Set-based updates bypass versioning, so the template item carries the audit trail instead."""
	if not (counts["created"] or counts["updated"] or counts["queued"]):
		return

	frappe.get_doc("Item", item_template).add_comment(
		"Comment",
		_("Bulk pricing by {0}: {1} created, {2} updated, {3} skipped, {4} queued").format(
			frappe.session.user, counts["created"], counts["updated"], counts["skipped"], counts["queued"]
		),
	)
