"""Keep the indexed card prices fresh when an Item Price or the price lists of a market change."""

import frappe
from frappe.query_builder import DocType

from commera.plugin_events import get_transaction_batch
from commera.search import price_seq
from commera.search.build import enqueue_full_rebuild
from commera.search.price_markets import fresh_price_markets, price_lists_of
from commera.search.source_sync import PRODUCT_DOCTYPE, queue_variants
from commera.search.sync import skip_batch_sync

PENDING_PRICES_FLAG = "commera_search_pending_prices"
PENDING_PRICE_LISTS_FLAG = "commera_search_pending_price_lists"


def on_item_price_change(doc, method=None):
	"""Item Price on_update and on_trash: reindex the products whose sizes it prices."""
	# Blind to in_import, as in source_sync: no importer re-syncs the products of the prices it saved.
	if skip_batch_sync():
		return
	# An edit can move a price to another item or list: the old one loses it.
	pending = get_transaction_batch(PENDING_PRICES_FLAG, set, reindex_pending_prices)
	pending.update(
		(version.item_code, version.price_list)
		for version in (doc.get_doc_before_save(), doc)
		if version and is_base_price(version)
	)


def on_item_price_rename(doc, method=None, old=None, new=None, merge=False):
	"""A merge deletes `old` through on_trash; this queues the price that remains."""
	on_item_price_change(doc)


def reindex_pending_prices():
	"""After the commit, so the indexed lists are read from a snapshot that has it: a list switch
	committed earlier shows here, and one committed later rebuilds from a read that has this price."""
	pending = frappe.local.flags.pop(PENDING_PRICES_FLAG, None) or set()
	indexed = set(price_lists_of(fresh_price_markets()))
	item_codes = sorted({item_code for item_code, price_list in pending if price_list in indexed})
	variants = get_published_variants(item_codes) if item_codes else []
	if variants:
		price_seq.bump_price_seq()
		queue_variants(variants)


def on_price_list_rename(doc, method=None, old=None, new=None, merge=False):
	"""A rename moves Item Prices and the market links by SQL, and a merge adds `old`'s prices."""
	if not skip_batch_sync():
		get_transaction_batch(PENDING_PRICE_LISTS_FLAG, set, rebuild_if_lists_indexed).add(new)


def rebuild_if_lists_indexed():
	renamed = frappe.local.flags.pop(PENDING_PRICE_LISTS_FLAG, None) or set()
	if renamed & set(price_lists_of(fresh_price_markets())):
		price_seq.bump_price_seq()
		enqueue_full_rebuild(deduplicate=True)


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
	price_seq.bump_price_seq_after_commit()
	enqueue_full_rebuild(deduplicate=True)


def get_market_price_lists(market) -> tuple | None:
	"""The lists the index prices a market doc with, or None: disabled, or the store's prices."""
	if not market or not market.enabled or not market.get("sale_price_list"):
		return None
	return market.sale_price_list, market.get("compare_at_price_list")
