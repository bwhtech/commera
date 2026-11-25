"""Database indexes for Commera's storefront, cart, checkout, and admin hot paths."""

import frappe

# (doctype, columns, index_name)
PERFORMANCE_INDEXES: tuple[tuple[str, list[str], str], ...] = (
	# Storefront catalog, PDP, recommendations, and sitemap reads on Style Attribute Variant
	("Style Attribute Variant", ["is_published", "route"], "idx_sav_pub_route"),
	("Style Attribute Variant", ["is_published", "name"], "idx_sav_pub_name"),
	("Style Attribute Variant", ["is_published", "modified"], "idx_sav_pub_modified"),
	("Style Attribute Variant", ["configurator", "is_published"], "idx_sav_config_pub"),
	("Style Attribute Variant", ["is_published", "item_group"], "idx_sav_pub_group"),
	("Style Attribute Variant", ["is_published", "attribute_value"], "idx_sav_pub_attr"),
	("Style Attribute Variant", ["item_style"], "idx_sav_item_style"),
	# Variant size lookups (cart, orders, inventory, PDP, listing filters)
	("Color Size Item", ["parenttype", "item_code"], "idx_csi_parenttype_item"),
	("Color Size Item", ["parent", "parenttype", "idx"], "idx_csi_parent_type_idx"),
	("Color Size Item", ["parenttype", "parent", "item_code", "size"], "idx_csi_cover_parent_item_size"),
	("Color Size Item", ["size", "parent"], "idx_csi_size_parent"),
	("Style Attribute Configurator", ["item_template", "name"], "idx_sac_template_name"),
	("Product Collection", ["parenttype", "parentfield", "parent", "item_group"], "idx_pc_cover"),
	# Product card cover / hover image lookups
	("Website Slideshow Item", ["parent", "parenttype", "idx"], "idx_wsi_parent_type_idx"),
	# Product reviews (storefront PDP + own review lookup)
	("Product Review", ["variant", "is_published", "creation"], "idx_pr_variant_pub_creation"),
	("Product Review", ["variant", "owner"], "idx_pr_variant_owner"),
	# Pricing hot paths on ERPNext tables
	("Item Price", ["item_code", "price_list", "selling"], "idx_ip_item_pl_selling"),
	("Item Price", ["price_list", "selling", "item_code"], "idx_ip_pl_selling_item"),
	("UOM Conversion Factor", ["from_uom", "to_uom"], "idx_ucf_from_to"),
	("Item", ["brand", "disabled"], "idx_item_brand_disabled"),
	# Discounts
	("Commera Discount", ["enabled", "method"], "idx_cd_enabled_method"),
	# Navigation & collections
	("Ecommerce Category", ["enabled", "route_slug"], "idx_ec_enabled_slug"),
	("Ecommerce Category", ["enabled", "display_order"], "idx_ec_enabled_order"),
	("Ecommerce Category Item Group", ["parenttype", "parent", "idx"], "idx_ecig_parent_type_idx"),
	("Ecommerce Category Item Group", ["item_group"], "idx_ecig_item_group"),
	# Checkout & payments
	("Gateway Payment Request", ["ref_doctype", "ref_docname", "status"], "idx_gpr_ref_status"),
	("Quotation", ["custom_guest_cart_key", "order_type", "docstatus"], "idx_quot_guest_cart"),
	("Commera Cart", ["user", "modified"], "idx_cc_user_modified"),
	("Commera Cart", ["cart_key", "modified"], "idx_cc_key_modified"),
	("Portal User", ["user", "parent"], "idx_pu_user_parent"),
	# Orders & analytics
	("Sales Order", ["order_type", "docstatus", "transaction_date"], "idx_so_type_docstatus_date"),
	("Sales Order", ["order_type", "docstatus", "customer"], "idx_so_type_docstatus_cust"),
	("Sales Order", ["docstatus", "creation"], "idx_so_docstatus_creation"),
	("Storefront Analytics Event", ["creation", "event", "session_id"], "idx_sae_creation_event_sess"),
	("Storefront Analytics Event", ["creation", "event", "utm_source", "session_id"], "idx_sae_cover_all"),
	("Storefront Analytics Event", ["creation", "utm_source", "session_id"], "idx_sae_creation_utm_sess"),
	("Storefront Analytics Event", ["creation", "session_id"], "idx_sae_creation_sess"),
	("Storefront Analytics Event", ["event", "session_id", "creation"], "idx_sae_event_sess_creation"),
	("Storefront Analytics Event", ["order_id"], "idx_sae_order_id"),
	# Stock movements & inventory report
	("Stock Ledger Entry", ["warehouse", "is_cancelled", "posting_date", "posting_time"], "idx_sle_wh_cancel_dt"),
)


def ensure_performance_indexes():
	"""Idempotently create all hot-path indexes for tables that exist on this site."""
	for doctype, columns, index_name in PERFORMANCE_INDEXES:
		if not frappe.db.table_exists(doctype):
			continue
		if not all(frappe.db.has_column(doctype, col) for col in columns):
			continue
		frappe.db.add_index(doctype, columns, index_name=index_name)
