"""Keep product records fresh when the Item or Configurator they copy fields from changes."""

import frappe

from commera.plugin_events import get_transaction_batch
from commera.search.record_builder import (
	ITEM_FIELDS,
	fields_by_doctype,
	get_configured_content_fields,
	union_fields,
)
from commera.search.sync import enqueue_upsert_many, skip_batch_sync

PRODUCT_DOCTYPE = "Style Attribute Variant"
# The variant field that links each source doctype to its variants.
SOURCE_LINK_FIELDS = {"Item": "item_style", "Style Attribute Configurator": "configurator"}
PENDING_VARIANTS_FLAG = "commera_search_source_variants"


def on_source_update(doc, method=None):
	if doc.get_doc_before_save() and search_fields_changed(doc):
		queue_variants_of(doc)


def on_source_rename(doc, method=None, old=None, new=None, merge=False):
	# Records keep the Item name in their product detail.
	queue_variants_of(doc)


def search_fields_changed(doc):
	return any(doc.has_value_changed(field) for field in source_fields(doc.doctype))


def source_fields(doctype):
	"""The fields of `doctype` that product records copy."""
	configured = fields_by_doctype(get_configured_content_fields(), doctype)
	return union_fields(ITEM_FIELDS if doctype == "Item" else [], configured)


def queue_variants_of(doc):
	# Blind to in_import: no importer re-syncs the variants of the sources it saved.
	if skip_batch_sync():
		return
	variants = frappe.get_all(
		PRODUCT_DOCTYPE,
		filters={SOURCE_LINK_FIELDS[doc.doctype]: doc.name, "is_published": 1},
		pluck="name",
	)
	if variants:
		get_transaction_batch(PENDING_VARIANTS_FLAG, set, enqueue_pending_variants).update(variants)


def enqueue_pending_variants():
	variants = frappe.local.flags.pop(PENDING_VARIANTS_FLAG, None)
	if variants:
		enqueue_upsert_many(PRODUCT_DOCTYPE, sorted(variants))
