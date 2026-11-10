# Copyright (c) 2025, Frappe Technologies and contributors
# For license information, please see license.txt

from urllib.parse import quote

import frappe
from frappe.query_builder.functions import Max
from frappe.utils import cint, now
from frappe.utils.nestedset import NestedSet, update_move_node

from commera.commera_ecommerce.doctype.commera_settings.editor_input import require_safe_url
from commera.localization import url
from commera.utils import IN_CLAUSE_CHUNK_SIZE

ITEM_GROUP_LINK_DOCTYPE = "Ecommerce Category Item Group"

# root tab -> mega-menu column -> link. Deeper levels exist in no storefront theme.
MAX_MENU_DEPTH = 3


def root_filter():
	"""Roots hold NULL or ""; only ``frappe.get_all`` wraps the column in ``ifnull``, ``get_value`` does not."""
	return ["in", ["", None]]


class EcommerceCategory(NestedSet):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from commera.commera_ecommerce.doctype.ecommerce_category_item_group.ecommerce_category_item_group import (
			EcommerceCategoryItemGroup,
		)

		category_name: DF.Data
		description: DF.SmallText | None
		display_name: DF.Data
		display_order: DF.Int
		enabled: DF.Check
		icon: DF.Data | None
		image: DF.AttachImage | None
		is_group: DF.Check
		link_item_groups: DF.Table[EcommerceCategoryItemGroup]
		lft: DF.Int
		link_brand: DF.Link | None
		link_type: DF.Literal["", "Item Group", "Brand", "URL"]
		link_url: DF.Data | None
		meta_description: DF.SmallText | None
		meta_title: DF.Data | None
		noindex: DF.Check
		og_image: DF.AttachImage | None
		old_parent: DF.Link | None
		parent_ecommerce_category: DF.Link | None
		rgt: DF.Int
		route_slug: DF.Data | None

	# end: auto-generated types

	nsm_parent_field = "parent_ecommerce_category"

	def on_update(self):
		# Private flag: ERPNext's Account/Department read ignore_update_nsm and would skip their NSM bookkeeping.
		if self.flags.ignore_update_nsm or frappe.local.flags.ignore_ecommerce_category_nsm:
			# update_nsm compares old_parent to parent; left NULL both read as "no parent" and the lft/rgt band leaks.
			self.db_set("old_parent", self.parent_ecommerce_category or "", update_modified=False)
			return
		super().on_update()

	def on_trash(self, allow_root_deletion=False):
		# A root compares "" to "", so update_nsm runs no branch and the delete leaves its lft/rgt band as a hole.
		if not self.get(self.nsm_parent_field) and cint(self.rgt) < self.last_bound():
			self.validate_if_child_exists()
			update_move_node(self, self.nsm_parent_field)
		super().on_trash(allow_root_deletion)

	def last_bound(self):
		category = frappe.qb.DocType(self.doctype)
		return cint(frappe.qb.from_(category).select(Max(category.rgt)).run(pluck=True)[0])

	def validate(self):
		self.validate_route_slug()
		self.validate_link_target()
		self.validate_depth()
		self.set_defaults()

	def validate_link_target(self):
		"""Keep only the target the link type uses. Jinja autoescaping is off, so a `javascript:` URL is
		stored XSS, and the model is the only place covering the Desk, REST and fixture write paths."""
		if self.link_type != "Item Group":
			self.link_item_groups = []
		if self.link_type != "Brand":
			self.link_brand = None
		if self.link_type != "URL":
			self.link_url = None
			return

		self.link_url = require_safe_url(self.link_url, frappe._("URL is required."))

	def validate_route_slug(self):
		"""Only top-level entries own a storefront URL, so only they need a slug."""
		if self.parent_ecommerce_category:
			self.route_slug = None
			return

		self.route_slug = frappe.scrub(self.route_slug or self.category_name)

		duplicate = frappe.get_all(
			"Ecommerce Category",
			filters={
				"route_slug": self.route_slug,
				"name": ["!=", self.name],
				"parent_ecommerce_category": root_filter(),
			},
			limit=1,
			pluck="name",
		)
		if duplicate:
			frappe.throw(
				frappe._("Route slug '{0}' is already used by {1}").format(self.route_slug, duplicate[0])
			)

	def validate_depth(self):
		depth = get_depth(self.parent_ecommerce_category) + 1
		height = get_subtree_height(self.name) if not self.is_new() else 0
		if depth + height > MAX_MENU_DEPTH:
			frappe.throw(
				frappe._("Menus are limited to {0} levels — this move would push '{1}' past that.").format(
					MAX_MENU_DEPTH, self.display_name or self.category_name
				)
			)

	def set_defaults(self):
		if not self.display_name:
			self.display_name = self.category_name


def build_listing_href(root_slug, item_groups):
	"""Product listing URL for a menu entry's item groups, as the `?subcategory=` filter expects."""
	subcategory = quote(",".join(item_groups))
	if root_slug:
		return url(f"/products?category={root_slug}&subcategory={subcategory}")
	return url(f"/products?subcategory={subcategory}")


def get_depth(name):
	"""Level this entry sits on, counting from 1 — a top-level tab is 1, and an empty name is 0."""
	depth = 0
	while name and depth <= MAX_MENU_DEPTH:
		name = frappe.db.get_value("Ecommerce Category", name, "parent_ecommerce_category")
		depth += 1
	return depth


def get_subtree_height(name):
	"""Levels hanging below this entry — 0 for a leaf, 1 when it has children only."""
	height = 0
	names = [name]
	while names and height <= MAX_MENU_DEPTH:
		names = frappe.get_all(
			"Ecommerce Category", filters={"parent_ecommerce_category": ["in", names]}, pluck="name"
		)
		if names:
			height += 1
	return height


def get_item_groups_by_entry(entry_names):
	"""Item groups each menu entry links, keyed by entry and in the order the editor stored them."""
	item_groups_by_entry = {}
	for offset in range(0, len(entry_names), IN_CLAUSE_CHUNK_SIZE):
		rows = frappe.get_all(
			ITEM_GROUP_LINK_DOCTYPE,
			filters={
				"parenttype": "Ecommerce Category",
				"parent": ["in", entry_names[offset : offset + IN_CLAUSE_CHUNK_SIZE]],
			},
			fields=["parent", "item_group"],
			order_by="parent asc, idx asc",
		)
		for row in rows:
			item_groups_by_entry.setdefault(row.parent, []).append(row.item_group)
	return item_groups_by_entry


def add_item_group_links(item_groups_by_entry):
	"""Link the given item groups to the given menu entries, in the order they are passed."""
	already_linked = get_item_groups_by_entry(list(item_groups_by_entry))
	timestamp = now()

	for entry, item_groups in item_groups_by_entry.items():
		if already_linked.get(entry):
			continue

		for index, item_group in enumerate(item_groups, start=1):
			link = frappe.new_doc(ITEM_GROUP_LINK_DOCTYPE)
			link.parent = entry
			link.parenttype = "Ecommerce Category"
			link.parentfield = "link_item_groups"
			link.idx = index
			link.item_group = item_group
			link.creation = timestamp
			link.modified = timestamp
			link.owner = frappe.session.user
			link.modified_by = frappe.session.user
			link.db_insert()


def get_menu_tree(enabled_only=False):
	"""The whole menu as nested nodes, in one query."""
	filters = {"enabled": 1} if enabled_only else {}
	entries = frappe.get_all(
		"Ecommerce Category",
		filters=filters,
		fields=[
			"name",
			"category_name",
			"display_name",
			"parent_ecommerce_category",
			"enabled",
			"display_order",
			"route_slug",
			"link_type",
			"link_brand",
			"link_url",
			"icon",
			"image",
			"description",
			"meta_title",
			"meta_description",
			"og_image",
			"noindex",
			"lft",
		],
		order_by="lft asc",
	)
	if not entries:
		return []

	item_groups_by_entry = get_item_groups_by_entry([entry.name for entry in entries])
	nodes = {}
	roots = []
	for entry in entries:
		nodes[entry.name] = {
			"name": entry.name,
			"label": entry.display_name or entry.category_name,
			"parent": entry.parent_ecommerce_category or "",
			"route_slug": entry.route_slug or "",
			"link_type": entry.link_type or "",
			"item_groups": item_groups_by_entry.get(entry.name, []),
			"brand": entry.link_brand or "",
			"url": entry.link_url or "",
			"icon": entry.icon or "",
			"image": entry.image or "",
			"description": entry.description or "",
			"meta_title": entry.meta_title or "",
			"meta_description": entry.meta_description or "",
			"og_image": entry.og_image or "",
			# cint, not `or ""`: a Check field's 0 would blank out and leave the editor control indeterminate.
			"noindex": cint(entry.noindex),
			"visible": bool(entry.enabled),
			"display_order": entry.display_order,
			"children": [],
		}

	for entry in entries:
		node = nodes[entry.name]
		if not entry.parent_ecommerce_category:
			roots.append(node)
			continue
		parent = nodes.get(entry.parent_ecommerce_category)
		# A hidden entry takes its whole branch with it rather than promoting the children to tabs.
		if parent:
			parent["children"].append(node)

	for node in nodes.values():
		node["children"].sort(key=lambda child: (child["display_order"] or 0, child["label"]))
	roots.sort(key=lambda node: (node["display_order"] or 0, node["label"]))

	for root in roots:
		set_hrefs(root, root["route_slug"] or root["name"])

	return roots


def set_hrefs(node, root_slug):
	node["href"] = get_node_href(node, root_slug)
	for child in node["children"]:
		set_hrefs(child, root_slug)


def get_node_href(node, root_slug):
	if node["link_type"] == "URL":
		return url(node["url"]) or None
	if node["link_type"] == "Brand":
		return url(f"/products?brands={quote(node['brand'])}") if node["brand"] else None
	if node["link_type"] == "Item Group" and node["item_groups"]:
		return build_listing_href(root_slug, node["item_groups"])
	if not node["parent"]:
		return url(f"/products?category={root_slug}")
	return None


@frappe.whitelist()
def get_active_categories():
	"""Get all active categories ordered by display_order"""
	return frappe.get_all(
		"Ecommerce Category",
		filters={"enabled": 1},
		fields=[
			"name",
			"category_name",
			"display_name",
			"route_slug",
			"icon",
			"image",
			"display_order",
		],
		order_by="display_order asc, category_name asc",
	)


@frappe.whitelist()
def get_category_by_slug(slug: str):
	"""Get category details by route slug"""
	return frappe.get_all(
		"Ecommerce Category",
		filters={"route_slug": slug, "enabled": 1},
		fields=["name", "category_name", "display_name", "route_slug", "icon", "image"],
		limit=1,
	)
