# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe.query_builder import Case
from frappe.query_builder.functions import Count
from frappe.utils import cint, cstr
from frappe.utils.nestedset import get_descendants_of, get_root_of, rebuild_tree

from commera.commera_ecommerce.doctype.bulk_publish_variants.bulk_publish_variants import (
	PRODUCT_DOCTYPE,
	get_variants_to_publish,
	save_publish_state,
)
from commera.commera_ecommerce.doctype.commera_settings.editor_input import (
	parse_list,
	require_safe_url,
	require_value,
)
from commera.commera_ecommerce.doctype.ecommerce_category.ecommerce_category import (
	MAX_MENU_DEPTH,
	get_depth,
	get_menu_tree,
)
from commera.search.sync import enqueue_upsert, enqueue_upsert_many
from commera.shop_data import get_category_item_groups
from commera.utils import IN_CLAUSE_CHUNK_SIZE

PRODUCT_PAGE_LENGTH = 50
MAX_PRODUCT_PAGE_LENGTH = 200


def sibling_names(parent):
	return frappe.get_all(
		"Ecommerce Category",
		filters={"parent_ecommerce_category": parent or ""},
		order_by="display_order asc, display_name asc, name asc",
		pluck="name",
	)


def apply_order(ordered_names):
	category = frappe.qb.DocType("Ecommerce Category")

	for offset in range(0, len(ordered_names), IN_CLAUSE_CHUNK_SIZE):
		chunk = ordered_names[offset : offset + IN_CLAUSE_CHUNK_SIZE]
		display_order = Case()
		for index, name in enumerate(chunk, start=offset + 1):
			display_order = display_order.when(category.name == name, index)

		(
			frappe.qb.update(category)
			.set(category.display_order, display_order)
			.where(category.name.isin(chunk))
			.run()
		)

	if ordered_names:
		frappe.clear_document_cache("Ecommerce Category")


def next_order(parent):
	rows = frappe.get_all(
		"Ecommerce Category", filters={"parent_ecommerce_category": parent or ""}, pluck="display_order"
	)
	return max([row or 0 for row in rows], default=0) + 1


def get_unique_category_name(parent, display_name):
	base = f"{parent} - {display_name}" if parent else display_name
	base = base[:130]
	candidate = base
	suffix = 2
	while frappe.db.exists("Ecommerce Category", candidate):
		candidate = f"{base} {suffix}"
		suffix += 1
	return candidate


def set_link(doc, link_type, link_target):
	doc.link_type = link_type or ""
	doc.link_item_groups = []
	doc.link_brand = None
	doc.link_url = None

	if link_type == "Item Group":
		for item_group in parse_list(link_target):
			doc.append("link_item_groups", {"item_group": item_group})
	elif link_type == "Brand":
		doc.link_brand = link_target
	elif link_type == "URL":
		doc.link_url = require_safe_url(link_target, frappe._("URL is required."))
	elif link_type:
		frappe.throw(frappe._("Unsupported link type: {0}").format(link_type))


def set_optional_fields(doc, values):
	for fieldname, value in values.items():
		if value is not None:
			doc.set(fieldname, value)


@frappe.whitelist()
def get_menu_editor_data():
	frappe.has_permission("Ecommerce Category", "read", throw=True)
	return {"menu": get_menu_tree()}


def mark_as_group(name):
	if name and not frappe.db.get_value("Ecommerce Category", name, "is_group"):
		frappe.db.set_value("Ecommerce Category", name, "is_group", 1)


def create_node(parent, display_name, link_type=None, link_target=None, display_order=None):
	doc = frappe.new_doc("Ecommerce Category")
	doc.category_name = get_unique_category_name(parent, display_name)
	doc.display_name = display_name
	doc.parent_ecommerce_category = parent or None
	doc.enabled = 1
	doc.display_order = next_order(parent) if display_order is None else display_order
	set_link(doc, link_type, link_target)
	doc.insert()

	mark_as_group(parent)
	return doc


@frappe.whitelist(methods=["POST"])
def add_node(
	parent: str | None = None,
	display_name: str | None = None,
	link_type: str | None = None,
	link_target: str | list | None = None,
):
	frappe.has_permission("Ecommerce Category", "create", throw=True)

	display_name = require_value(display_name, frappe._("Display name is required."))
	create_node((parent or "").strip(), display_name, link_type, link_target)

	return get_menu_editor_data()


@frappe.whitelist(methods=["POST"])
def update_node(
	name: str,
	display_name: str | None = None,
	link_type: str | None = None,
	link_target: str | list | None = None,
	route_slug: str | None = None,
	icon: str | None = None,
	image: str | None = None,
	meta_title: str | None = None,
	meta_description: str | None = None,
	og_image: str | None = None,
	noindex: int | str | None = None,
):
	frappe.has_permission("Ecommerce Category", "write", throw=True)

	doc = frappe.get_doc("Ecommerce Category", name)
	if display_name is not None:
		doc.display_name = require_value(display_name, frappe._("Display name is required."))
	if route_slug is not None:
		doc.route_slug = require_value(route_slug, frappe._("URL is required."))
	if link_type is not None:
		set_link(doc, link_type, link_target)
	set_optional_fields(
		doc,
		{
			"icon": icon,
			"image": image,
			"meta_title": meta_title,
			"meta_description": meta_description,
			"og_image": og_image,
			"noindex": None if noindex is None else cint(noindex),
		},
	)
	doc.save()

	return get_menu_editor_data()


def get_subtree_names(name):
	descendants = get_descendants_of("Ecommerce Category", name, ignore_permissions=True)
	return [*descendants, name]


def count_descendants(name):
	lft, rgt = frappe.db.get_value("Ecommerce Category", name, ["lft", "rgt"])
	return frappe.db.count("Ecommerce Category", {"lft": (">", lft), "rgt": ("<", rgt)})


@frappe.whitelist()
def get_delete_preview(name: str):
	frappe.has_permission("Ecommerce Category", "read", throw=True)

	node = get_menu_node(name)
	return {"label": node["label"], "count": count_descendants(node["name"])}


@frappe.whitelist(methods=["POST"])
def delete_node(name: str):
	frappe.has_permission("Ecommerce Category", "delete", throw=True)

	for entry in get_subtree_names(name):
		frappe.delete_doc("Ecommerce Category", entry)

	return get_menu_editor_data()


@frappe.whitelist()
def get_delete_all_preview():
	frappe.has_permission("Ecommerce Category", "read", throw=True)

	return {"count": frappe.db.count("Ecommerce Category")}


@frappe.whitelist(methods=["POST"])
def delete_all_nodes():
	frappe.has_permission("Ecommerce Category", "delete", throw=True)

	names = frappe.get_all("Ecommerce Category", pluck="name", order_by="lft desc")
	for name in names:
		frappe.delete_doc("Ecommerce Category", name, ignore_on_trash=True)

	enqueue_upsert_many("Ecommerce Category", names)

	return get_menu_editor_data()


@frappe.whitelist(methods=["POST"])
def reorder_nodes(parent: str, ordered_names: list | str):
	frappe.has_permission("Ecommerce Category", "write", throw=True)
	ordered_names = parse_list(ordered_names)

	siblings = set(
		frappe.get_all(
			"Ecommerce Category", filters={"parent_ecommerce_category": parent or ""}, pluck="name"
		)
	)
	missing = [name for name in ordered_names if name not in siblings]
	if missing:
		frappe.throw(frappe._("Unknown menu entr(y/ies): {0}").format(", ".join(missing)))

	apply_order(ordered_names)

	return get_menu_editor_data()


@frappe.whitelist(methods=["POST"])
def move_node(name: str, to_parent: str | None = None, target_index: int | str = 0):
	frappe.has_permission("Ecommerce Category", "write", throw=True)

	to_parent = (to_parent or "").strip()
	doc = frappe.get_doc("Ecommerce Category", name)
	from_parent = doc.parent_ecommerce_category or ""

	doc.parent_ecommerce_category = to_parent or None
	doc.save()

	mark_as_group(to_parent)

	apply_order(sibling_names(from_parent))

	ordered_names = [sibling for sibling in sibling_names(to_parent) if sibling != name]
	target_index = max(0, min(cint(target_index), len(ordered_names)))
	ordered_names.insert(target_index, name)
	apply_order(ordered_names)

	return get_menu_editor_data()


def get_source_item_groups(item_group):
	if item_group:
		roots = frappe.get_all("Item Group", filters={"name": item_group}, fields=["name", "lft", "rgt"])
		if not roots:
			frappe.throw(frappe._("Item Group '{0}' not found.").format(item_group))
	else:
		roots = frappe.get_all(
			"Item Group",
			filters={"parent_item_group": get_root_of("Item Group")},
			fields=["name", "lft", "rgt"],
			order_by="lft asc",
		)
	if not roots:
		return [], []

	item_group_table = frappe.qb.DocType("Item Group")
	within_any_root = None
	for root in roots:
		within_root = (item_group_table.lft >= root.lft) & (item_group_table.rgt <= root.rgt)
		within_any_root = within_root if within_any_root is None else (within_any_root | within_root)

	rows = (
		frappe.qb.from_(item_group_table)
		.select(item_group_table.name, item_group_table.item_group_name, item_group_table.parent_item_group)
		.where(within_any_root)
		.orderby(item_group_table.lft)
		.run(as_dict=True)
	)
	return [root.name for root in roots], rows


def get_linked_nodes():
	linked = {}

	def index(node):
		for item_group in node["item_groups"]:
			linked[(node["parent"], item_group)] = node["name"]
		for child in node["children"]:
			index(child)

	for root in get_menu_tree():
		index(root)
	return linked


def seed_categories_from_item_groups(item_group=None, parent=""):
	"""Copy the Item Group tree into the menu - a one-time copy, never a live mirror, and safe to re-run."""
	root_names, source_groups = get_source_item_groups(item_group)
	if not source_groups:
		return

	linked_nodes = get_linked_nodes()
	base_level = get_depth(parent) + 1
	root_names = set(root_names)

	node_for_group = {}
	level_for_group = {}
	next_display_order = {}

	previous_flag = frappe.local.flags.ignore_ecommerce_category_nsm
	frappe.local.flags.ignore_ecommerce_category_nsm = True
	try:
		for group in source_groups:
			if group.name in root_names:
				menu_parent, level = parent, base_level
			elif group.parent_item_group in node_for_group:
				menu_parent = node_for_group[group.parent_item_group]
				level = level_for_group[group.parent_item_group] + 1
			else:
				continue

			if level > MAX_MENU_DEPTH:
				continue

			existing = linked_nodes.get((menu_parent, group.name))
			if existing:
				node_for_group[group.name] = existing
			else:
				if menu_parent not in next_display_order:
					next_display_order[menu_parent] = next_order(menu_parent)
				node_for_group[group.name] = create_node(
					menu_parent,
					group.item_group_name or group.name,
					"Item Group",
					[group.name],
					display_order=next_display_order[menu_parent],
				).name
				next_display_order[menu_parent] += 1
			level_for_group[group.name] = level

		rebuild_tree("Ecommerce Category")
	finally:
		frappe.local.flags.ignore_ecommerce_category_nsm = previous_flag


def seed_menu_when_empty():
	"""Give a store with no menu one copied from its Item Group tree. Install and upgrade only - never
	on every migrate, or a menu the shop owner emptied on purpose gets refilled."""
	if frappe.db.count("Ecommerce Category"):
		return

	seed_categories_from_item_groups()


@frappe.whitelist(methods=["POST"])
def import_from_item_group(item_group: str | None = None, parent: str | None = None):
	frappe.has_permission("Ecommerce Category", "create", throw=True)

	seed_categories_from_item_groups(item_group, (parent or "").strip())

	return get_menu_editor_data()


@frappe.whitelist(methods=["POST"])
def set_visibility(name: str, visible: int | str):
	frappe.has_permission("Ecommerce Category", "write", throw=True)

	frappe.db.set_value("Ecommerce Category", name, "enabled", cint(visible))

	enqueue_upsert("Ecommerce Category", name)

	return get_menu_editor_data()


def find_menu_node(name):
	name = cstr(name)
	pending = list(get_menu_tree())
	while pending:
		node = pending.pop()
		if cstr(node["name"]) == name:
			return node
		pending.extend(node["children"])
	return None


def get_menu_node(name):
	node = find_menu_node(name)
	if not node:
		frappe.throw(frappe._("Menu entry '{0}' not found.").format(name))
	return node


def get_cascade_scope(name):
	node = get_menu_node(name)
	return node["label"], get_category_item_groups(node)


def get_cascade_counts(item_groups):
	publishable = get_variants_to_publish(1, item_groups=item_groups)
	waiting = get_variants_to_publish(1, item_groups=item_groups, require_complete=False)
	return {
		"publishable": len(publishable),
		"incomplete": len(waiting) - len(publishable),
		"published": len(get_variants_to_publish(0, item_groups=item_groups)),
	}


def get_item_group_filter(variant, item_groups):
	condition = None
	for offset in range(0, len(item_groups), IN_CLAUSE_CHUNK_SIZE):
		chunk = variant.item_group.isin(item_groups[offset : offset + IN_CLAUSE_CHUNK_SIZE])
		condition = chunk if condition is None else (condition | chunk)
	return condition


def get_search_filter(variant, search):
	pattern = f"%{search}%"
	return variant.display_name.like(pattern) | variant.item_group.like(pattern)


def count_cascade_matches(item_groups, search):
	variant = frappe.qb.DocType(PRODUCT_DOCTYPE)
	rows = (
		frappe.qb.from_(variant)
		.select(Count("*").as_("matches"))
		.where(get_item_group_filter(variant, item_groups) & get_search_filter(variant, search))
		.run(as_dict=True)
	)
	return cint(rows[0].matches) if rows else 0


def get_cascade_page(item_groups, start, page_length, search=None):
	variant = frappe.qb.DocType(PRODUCT_DOCTYPE)
	condition = get_item_group_filter(variant, item_groups)
	if search:
		condition = condition & get_search_filter(variant, search)

	rows = (
		frappe.qb.from_(variant)
		.select(variant.name, variant.display_name, variant.item_group, variant.is_published)
		.where(condition)
		.orderby(variant.item_group)
		.orderby(variant.name)
		.limit(page_length)
		.offset(start)
		.run(as_dict=True)
	)
	if not rows:
		return []

	publishable = {cstr(name) for name in get_variants_to_publish(1, names=[row.name for row in rows])}
	return [
		{
			"name": row.name,
			"display_name": row.display_name or cstr(row.name),
			"item_group": row.item_group,
			"is_published": cint(row.is_published),
			"blocked_reason": ""
			if cint(row.is_published) or cstr(row.name) in publishable
			else frappe._("Missing images or sizes"),
		}
		for row in rows
	]


@frappe.whitelist()
def get_cascade_products(
	name: str, start: int | str = 0, page_length: int | str = PRODUCT_PAGE_LENGTH, search: str | None = None
):
	frappe.has_permission("Ecommerce Category", "read", throw=True)
	frappe.has_permission(PRODUCT_DOCTYPE, "read", throw=True)

	start = max(0, cint(start))
	page_length = min(max(1, cint(page_length)), MAX_PRODUCT_PAGE_LENGTH)
	search = cstr(search).strip()

	label, item_groups = get_cascade_scope(name)
	counts = get_cascade_counts(item_groups)
	total = counts["publishable"] + counts["incomplete"] + counts["published"]
	return {
		"label": label,
		"total": total,
		**counts,
		"start": start,
		"matching": count_cascade_matches(item_groups, search) if item_groups and search else total,
		"products": get_cascade_page(item_groups, start, page_length, search) if item_groups else [],
	}


@frappe.whitelist()
def get_publish_preview(name: str, publish: int | str):
	frappe.has_permission("Ecommerce Category", "read", throw=True)
	frappe.has_permission(PRODUCT_DOCTYPE, "write", throw=True)

	label, item_groups = get_cascade_scope(name)
	return {"count": len(get_variants_to_publish(cint(publish), item_groups=item_groups)), "label": label}


@frappe.whitelist(methods=["POST"])
def set_published(
	name: str,
	publish: int | str,
	excluded_names: list | str | None = None,
	included_names: list | str | None = None,
):
	frappe.has_permission("Ecommerce Category", "read", throw=True)
	frappe.has_permission(PRODUCT_DOCTYPE, "write", throw=True)

	publish = cint(publish)
	_label, item_groups = get_cascade_scope(name)
	changed_names = get_variants_to_publish(publish, item_groups=item_groups)

	if included_names is not None:
		included = {cstr(value) for value in parse_list(included_names)}
		changed_names = [variant for variant in changed_names if cstr(variant) in included]

	excluded = {cstr(value) for value in parse_list(excluded_names)}
	if excluded:
		changed_names = [variant for variant in changed_names if cstr(variant) not in excluded]

	save_publish_state(publish, changed_names)

	return {"menu": get_menu_editor_data()["menu"], "count": len(changed_names)}
