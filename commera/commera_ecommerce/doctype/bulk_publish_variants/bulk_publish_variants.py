# Copyright (c) 2025, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.query_builder import DocType
from frappe.utils import cint, create_batch

from commera.app_events import add_changed_products
from commera.commera_ecommerce.doctype.commera_settings.editor_input import parse_list
from commera.search.sync import enqueue_upsert_many
from commera.utils import IN_CLAUSE_CHUNK_SIZE

PRODUCT_DOCTYPE = "Style Attribute Variant"


def chunked(values):
	"""Batches of names small enough for one IN (...), or [None] meaning "do not filter on this"."""
	if values is None:
		return [None]
	return create_batch(list(values), IN_CLAUSE_CHUNK_SIZE)


def get_variants_to_publish(publish, names=None, item_groups=None, require_complete=True):
	"""Variants whose `is_published` this call would flip. Completeness is demanded only on the way in -
	an already-live variant must always be unpublishable."""
	variant = frappe.qb.DocType(PRODUCT_DOCTYPE)
	slideshow_item = frappe.qb.DocType("Website Slideshow Item")
	color_size_item = frappe.qb.DocType("Color Size Item")

	found = []
	for name_chunk in chunked(names):
		for item_group_chunk in chunked(item_groups):
			query = frappe.qb.from_(variant)
			if publish and require_complete:
				query = (
					query.inner_join(slideshow_item)
					.on(
						(slideshow_item.parent == variant.name)
						& (slideshow_item.parenttype == PRODUCT_DOCTYPE)
					)
					.inner_join(color_size_item)
					.on(
						(color_size_item.parent == variant.name)
						& (color_size_item.parenttype == PRODUCT_DOCTYPE)
					)
				)
			query = query.select(variant.name).distinct().where(variant.is_published == (0 if publish else 1))
			if name_chunk is not None:
				query = query.where(variant.name.isin(name_chunk))
			if item_group_chunk is not None:
				query = query.where(variant.item_group.isin(item_group_chunk))
			found.extend(row.name for row in query.run(as_dict=True))

	return list(dict.fromkeys(found))


def save_publish_state(publish, changed_names):
	"""The one place `is_published` is written in bulk, and so the one place the index is told:
	`frappe.db.set_value` fires no document event, so `sync.on_update` never runs."""
	item_templates = set()
	for chunk in create_batch(changed_names, IN_CLAUSE_CHUNK_SIZE):
		frappe.db.set_value(PRODUCT_DOCTYPE, {"name": ["in", chunk]}, {"is_published": publish})
		item_templates.update(
			frappe.get_all(
				PRODUCT_DOCTYPE, filters={"name": ["in", chunk]}, pluck="item_style", distinct=True
			)
		)

	enqueue_upsert_many(PRODUCT_DOCTYPE, changed_names)
	add_changed_products(item_templates, "published")

	return changed_names


def publish_variants(publish, names=None, item_groups=None):
	return save_publish_state(publish, get_variants_to_publish(publish, names=names, item_groups=item_groups))


@frappe.whitelist(methods=["POST"])
def set_variants_published(publish: int | str, names: list | str):
	"""Publish or unpublish exactly the variants named: `bulk_toggle_publish` ANDs this Single's stored
	filter fields in, which would silently shrink an explicit selection."""
	frappe.has_permission(PRODUCT_DOCTYPE, "write", throw=True)

	names = parse_list(names)
	if not names:
		return {"updated_count": 0}

	return {"updated_count": len(publish_variants(cint(publish), names=names))}


class BulkPublishVariants(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		brand: DF.Link | None
		dcs: DF.Data | None
		item_code: DF.Data | None
		season_code: DF.Data | None
		vendor_code: DF.Data | None
	# end: auto-generated types

	@frappe.whitelist(methods=["POST"])
	def bulk_toggle_publish(
		self,
		publish: bool = True,
		style_attribute_variant_list: list[str] | None = None,
	):
		style_attribute_variant = DocType(PRODUCT_DOCTYPE)
		color_size_item = DocType("Color Size Item")
		child_item = DocType("Item").as_("child_item")
		style_item = DocType("Item").as_("style_item")
		item_attr = DocType("Item Variant Attribute")

		query = (
			frappe.qb.from_(style_attribute_variant)
			.left_join(color_size_item)
			.on(color_size_item.parent == style_attribute_variant.name)
			.left_join(child_item)
			.on(child_item.name == color_size_item.item_code)
			.left_join(style_item)
			.on(style_item.name == style_attribute_variant.item_style)
			.left_join(item_attr)
			.on(item_attr.parent == child_item.name)
		)
		if style_attribute_variant_list:
			query = query.where(style_attribute_variant.name.isin(style_attribute_variant_list))
		if self.vendor_code:
			query = query.where(
				(style_item.custom_vendor_code == self.vendor_code)
				| (child_item.custom_vendor_code == self.vendor_code)
			)
		if self.dcs:
			query = query.where((style_item.custom_dcs == self.dcs) | (child_item.custom_dcs == self.dcs))
		if self.brand:
			query = query.where((style_item.brand == self.brand) | (child_item.brand == self.brand))
		if self.item_code:
			query = query.where((style_item.name == self.item_code) | (style_item.name == self.item_code))
		if self.season_code:
			query = query.where(
				(item_attr.attribute == "Season") & (item_attr.attribute_value == self.season_code)
			)

		query = query.select(style_attribute_variant.name)
		query = query.distinct()
		matched_names = [row["name"] for row in query.run(as_dict=True)]
		changed_names = publish_variants(publish, names=matched_names) if matched_names else []

		return {"updated_count": len(changed_names), "total_matched": len(matched_names)}
