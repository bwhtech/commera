"""Database indexes for Commera's storefront, cart, checkout, and admin hot paths.
Scoped exclusively to Commera-owned tables so bench migrate never runs long ALTERs on core ERPNext tables."""

import frappe

# (doctype, columns, index_name)
PERFORMANCE_INDEXES: tuple[tuple[str, list[str], str], ...] = (
	# Storefront catalog, PDP, and sibling options on Style Attribute Variant
	("Style Attribute Variant", ["is_published", "route"], "idx_sav_pub_route"),
	("Style Attribute Variant", ["is_published", "item_group"], "idx_sav_pub_group"),
	("Style Attribute Variant", ["configurator", "is_published"], "idx_sav_config_pub"),
	("Style Attribute Variant", ["item_style"], "idx_sav_item_style"),
	# Variant size lookups (cart, orders, inventory, PDP, listing filters)
	("Color Size Item", ["parenttype", "item_code"], "idx_csi_parenttype_item"),
	("Color Size Item", ["parenttype", "parent", "item_code", "size"], "idx_csi_cover_parent_item_size"),
	("Product Collection", ["parenttype", "parentfield", "parent", "item_group"], "idx_pc_cover"),
	# Product reviews (storefront PDP + own review lookup)
	("Product Review", ["variant", "is_published", "creation"], "idx_pr_variant_pub_creation"),
	("Product Review", ["variant", "owner"], "idx_pr_variant_owner"),
	# Discounts & navigation
	("Commera Discount", ["enabled", "method"], "idx_cd_enabled_method"),
	("Ecommerce Category", ["enabled", "route_slug"], "idx_ec_enabled_slug"),
	("Ecommerce Category Item Group", ["item_group"], "idx_ecig_item_group"),
	# Checkout & cart lookups
	("Gateway Payment Request", ["ref_doctype", "ref_docname", "status"], "idx_gpr_ref_status"),
	("Commera Cart", ["user", "modified"], "idx_cc_user_modified"),
	("Commera Cart", ["cart_key", "modified"], "idx_cc_key_modified"),
	# Storefront analytics funnels & order attribution
	(
		"Storefront Analytics Event",
		["creation", "event", "utm_source", "session_id"],
		"idx_sae_creation_event_utm_sess",
	),
	("Storefront Analytics Event", ["order_id"], "idx_sae_order_id"),
)


def ensure_performance_indexes():
	"""Idempotently create hot-path indexes for Commera tables that exist on this site."""
	for doctype, columns, index_name in PERFORMANCE_INDEXES:
		if not frappe.db.table_exists(doctype):
			continue
		if not all(frappe.db.has_column(doctype, col) for col in columns):
			continue
		frappe.db.add_index(doctype, columns, index_name=index_name)
