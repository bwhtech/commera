"""Keep the indexed card prices fresh when an Item Price or the price lists of a market change."""

import frappe
from frappe.query_builder import DocType

from commera.search.build import enqueue_full_rebuild
from commera.search.price_markets import get_price_markets
from commera.search.price_seq import bump_price_seq_after_commit
from commera.search.source_sync import PRODUCT_DOCTYPE, queue_variants
from commera.search.sync import skip_batch_sync


def on_item_price_change(doc, method=None):
	"""Item Price on_update and on_trash: reindex the products whose sizes it prices."""
	# Blind to in_import, as in source_sync: no importer re-syncs the products of the prices it saved.
	if skip_batch_sync():
		return
	price_lists = {name for prices in get_price_markets().values() for name in prices.price_lists}
	# An edit can move a price to another item or list: the old one loses it.
	item_codes = {
		version.item_code
		for version in (doc.get_doc_before_save(), doc)
		if version and version.price_list in price_lists and is_base_price(version)
	}
	if item_codes:
		bump_price_seq_after_commit()
		queue_variants(get_published_variants(sorted(item_codes)))


def is_base_price(item_price) -> bool:
	"""base_prices.BASE_PRICE_FILTERS on a document."""
	return not item_price.get("customer") and not item_price.get("batch_no")


def get_published_variants(item_codes: list[str]) -> list[str]:
	size = DocType("Color Size Item")
	variant = DocType(PRODUCT_DOCTYPE)
	return (
		frappe.qb.from_(size)
		.join(variant)
		.on(variant.name == size.parent)
		.select(size.parent)
		.distinct()
		.where(
			(size.parenttype == PRODUCT_DOCTYPE)
			& size.item_code.isin(item_codes)
			& (variant.is_published == 1)
		)
		.run(pluck=True)
	)


def rebuild_if_market_prices_change(before, after):
	"""Commera Market on_update and on_trash. Every product has a row per market, so rebuild."""
	if skip_batch_sync() or get_market_price_lists(before) == get_market_price_lists(after):
		return
	bump_price_seq_after_commit()
	enqueue_full_rebuild(deduplicate=True)


def get_market_price_lists(market) -> tuple | None:
	"""The lists the index prices a market doc with, or None: disabled, or the store's prices."""
	if not market or not market.enabled or not market.get("sale_price_list"):
		return None
	return market.sale_price_list, market.get("compare_at_price_list")
