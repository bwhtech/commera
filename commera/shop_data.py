# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe

from commera.branding import get_brand_assets
from commera.commera_ecommerce.doctype.ecommerce_category.ecommerce_category import get_menu_tree


def get_storefront_menu():
	"""Request-scoped enabled menu tree, memoised on `frappe.local`."""
	menu = getattr(frappe.local, "commera_storefront_menu", None)
	if menu is None:
		menu = get_menu_tree(enabled_only=True)
		frappe.local.commera_storefront_menu = menu
	return menu


def find_menu_root(menu, category):
	"""Locate the tab a `?category=` value names — it carries the route slug, the entry name or the label."""
	for node in menu:
		if category in (node["route_slug"], node["name"], node["label"]):
			return node
	return None


def build_facet_node(node):
	"""One sidebar facet, or None when the entry can never filter the listing."""
	children = build_facet_nodes(node["children"])
	# A URL or Brand entry links no item group: its facet would filter on the empty string.
	if not node["item_groups"] and not children:
		return None
	return {
		"item_groups": node["item_groups"],
		"display_name": node["label"],
		"children": children,
		"is_leaf": int(not children),
	}


def build_facet_nodes(nodes):
	facets = [build_facet_node(node) for node in nodes]
	return [facet for facet in facets if facet]


def get_category_tree(root_category):
	"""Facet subtree for one menu tab, so the sidebar and the navbar always agree."""
	root = find_menu_root(get_storefront_menu(), root_category)
	facet = build_facet_node(root) if root else None
	if not facet:
		return {
			"name": root_category,
			"display_name": root_category,
			"children": [],
			"is_leaf": 1,
		}
	return facet


def get_category_facets(category):
	"""Sidebar facets for the listing: one tab's columns, or every tab keyed by its label."""
	menu = get_storefront_menu()
	if category:
		root = find_menu_root(menu, category)
		return {root["label"]: build_facet_nodes(root["children"])} if root else {}
	return {root["label"]: build_facet_nodes(root["children"]) for root in menu}


def as_legacy_item_group(node):
	"""Shape one menu entry the way the pre-tree headers read an Item Group row.

	`name` is the `?subcategory=` value, which the listing filter reads as a comma-separated list.
	"""
	return frappe._dict(
		name=",".join(node["item_groups"]) or node["name"],
		display_name=node["label"],
	)


def build_legacy_navigation(menu):
	"""The pre-tree `navigation_categories` shape, now fed by the menu tree."""
	navigation_categories = []
	for root in menu:
		child_category_sections = []
		has_mega_menu = False
		for child in root["children"]:
			grandchild_item_groups = [as_legacy_item_group(grandchild) for grandchild in child["children"]]
			child_category_sections.append(
				frappe._dict(
					child_item_group=as_legacy_item_group(child),
					grandchild_item_groups=grandchild_item_groups,
				)
			)
			if grandchild_item_groups:
				has_mega_menu = True

		navigation_categories.append(
			frappe._dict(
				category=frappe._dict(
					name=root["name"],
					display_name=root["label"],
					route_slug=root["route_slug"],
					href=root["href"],
				),
				child_category_sections=child_category_sections,
				child_item_groups=[as_legacy_item_group(child) for child in root["children"]],
				has_mega_menu=has_mega_menu,
			)
		)
	return navigation_categories


def get_featured_brands(menu):
	"""Brands the menu links to, deduped across the tree and ordered by first appearance."""
	brands = []
	pending = list(reversed(menu))
	while pending:
		node = pending.pop()
		if node["link_type"] == "Brand" and node["brand"] and node["brand"] not in brands:
			brands.append(node["brand"])
		pending.extend(reversed(node["children"]))
	return [frappe._dict(name=brand) for brand in brands]


def get_header_data():
	settings = frappe.get_cached_doc("Commera Settings", "Commera Settings")
	menu = get_storefront_menu()

	return frappe._dict(
		settings=settings,
		store_name=settings.store_name or "Commera",
		brand_logo=get_brand_assets().logo,
		navigation_menu=menu,
		navigation_categories=build_legacy_navigation(menu),
		featured_brands=get_featured_brands(menu),
		has_social_links=bool(
			settings.facebook_url
			or settings.twitter_url
			or settings.instagram_url
			or settings.tiktok_url
			or settings.snapchat_url
		),
	)
