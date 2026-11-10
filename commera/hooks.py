app_name = "commera"
app_title = "Commera"
app_publisher = "hussain@buildwithhussain.com"
app_description = "Ecommerce extension for ERPNext"
app_email = "rahul@buildwithhussain.com"
app_license = "agpl-3.0"

# frappe/payments deliberately absent: bwh_payments ships its own Payment Gateway Profile and base_class.
required_apps = ["frappe/erpnext", "bwhtech/bwh_payments"]


# Only language-independent rules: commera.localization.routing redirects /<default>/* and /account.
website_redirects = [
	{"source": "/en-US/(.*)", "target": r"/en/\1"},
	{"source": "/en-GB/(.*)", "target": r"/en/\1"},
]

# localize_request strips the language prefix off request.path before any app's path resolver runs,
# so the route rules below match the path without it. resolve_website_path sends the canonical redirects.
before_request = ["commera.localization.routing.localize_request"]
website_path_resolver = "commera.localization.routing.resolve_website_path"
# Frappe runs auth_hooks after its API key and OAuth checks, so a storefront API call knows its user.
auth_hooks = ["commera.localization.routing.localize_api_request"]

website_route_rules = [
	# SPA client-side routing: every /commera deep link resolves to the same shell so a reload does not 404.
	{"from_route": "/commera/<path:app_path>", "to_route": "/commera"},
	# -> Products
	{"from_route": "/products", "to_route": "/products/list.html"},
	{"from_route": "/products/<path:route>", "to_route": "/products/details.html"},
	# -> Cart / Checkout
	{"from_route": "/cart", "to_route": "/cart/cart.html"},
	{"from_route": "/cart/checkout", "to_route": "/cart/checkout.html"},
	{"from_route": "/cart/<path:codes>", "to_route": "/cart/permalink.html"},
	# -> Account
	{"from_route": "/account/dashboard", "to_route": "/account/dashboard.html"},
	{"from_route": "/account/profile", "to_route": "/account/profile.html"},
	{"from_route": "/account/orders", "to_route": "/account/orders/index.html"},
	{"from_route": "/account/orders/confirmation", "to_route": "/account/orders/confirmation.html"},
	{"from_route": "/account/orders/detail", "to_route": "/account/orders/detail.html"},
	{"from_route": "/account/wishlist", "to_route": "/account/wishlist.html"},
	{"from_route": "/account/address", "to_route": "/account/address.html"},
	# ------------
	# Crawl infrastructure (language-agnostic)
	# ------------
	{"from_route": "/sitemap-<seg_type>-<page>.xml", "to_route": "sitemap_segment.xml"},
	{"from_route": "/og-image/<path:route>", "to_route": "/og_image_render"},
]

on_session_creation = "commera.commera_ecommerce.doctype.commera_cart.commera_cart.keep_guest_cart"
on_login = "commera.roles.save_commera_default_app"

# Runs before every core renderer (frappe/website/path_resolver.py); the private-store gate must stay first.
page_renderer = [
	"commera.storefront_access.PrivateStorefrontPage",
	"commera.shop_themes.theme_resolver.ThemePageRenderer",
]

# frappe.clear_cache() flushes redis but not frappe.local, where the theme engine memoises - hence these.
clear_cache = [
	"commera.shop_themes.doctype.shop_theme.shop_theme.clear_theme_cache",
	"commera.shop_themes.doctype.shop_theme_settings.shop_theme_settings.clear_settings_cache",
	"commera.plugins.registry.clear_registry_cache",
	"commera.storefront_plugins.clear_storefront_plugin_cache",
]

# Without this, records of a custom doctype never import on migrate (frappe/model/sync.py).
importable_doctypes = ["Shop Theme"]

doctype_js = {
	"Item": ["public/js/extends/item.js", "public/js/extends/ecommerce_tab.js"],
	"Sales Order": "public/js/extends/sales_order.js",
	"Delivery Note": "public/js/extends/delivery_note.js",
	"Shipment": "public/js/extends/shipment.js",
	"Style Attribute Variant": "public/js/extends/seo_listing.js",
	"Ecommerce Category": "public/js/extends/seo_listing.js",
	"Commera Settings": [
		"public/js/extends/seo_listing.js",
		"public/js/extends/footer_manager.js",
		"public/js/extends/navbar_manager.js",
	],
}

after_install = ["commera.migrate.after_install", "commera.cloud.link.queue_initial_link"]
after_migrate = "commera.migrate.after_migrate"
before_uninstall = "commera.customizations.delete_customizations"
after_app_install = [
	"commera.storefront_plugins.sync_storefront_apps",
	"commera.shipping.providers.validate_providers",
]
before_app_uninstall = "commera.shipping.providers.disable_app_profiles"

commera_hooks = {
	"shipping_providers": ["Shiprocket Shipping Settings", "AfterShip Shipping Settings"],
	# Record fields merchants translate into Content Translation. Other apps add their own here.
	"translatable_resources": [
		{
			"type": "product",
			"doctype": "Style Attribute Variant",
			"fields": ["display_name", "description", "meta_title", "meta_description"],
			"label": "Products",
		},
		{
			"type": "collection",
			"doctype": "Ecommerce Category",
			"fields": ["display_name", "description", "meta_title", "meta_description"],
			"label": "Collections",
		},
		{
			"type": "page",
			"doctype": "Shop Web Page",
			"fields": ["title", "content", "meta_title", "meta_description"],
			"label": "Pages",
		},
		{
			"type": "footer_section",
			"doctype": "Footer Section Config",
			"fields": ["section_title"],
			"label": "Footer sections",
		},
		# Keyed by the row name, so a translation follows its link through edits and reorders.
		{"type": "footer_link", "doctype": "Footer Link", "fields": ["link_label"], "label": "Footer links"},
		# A Single: its translations name the doctype as the record.
		{
			"type": "shop",
			"doctype": "Commera Settings",
			"fields": ["store_name", "default_meta_description"],
			"label": "Shop",
		},
	],
}
setup_wizard_complete = [
	"commera.swatches.drop_unused_colour_attribute",
	"commera.cloud.link.queue_initial_link",
	"commera.plugin_events.add_plugin_user",
]

# Commera Webhooks: the handler counts only while an enabled webhook subscribes to the event.
commera_events = {
	event: ["commera.webhooks.deliver"]
	for event in (
		"order_placed",
		"order_paid",
		"order_cancelled",
		"order_refunded",
		"order_fulfilled",
		"order_delivered",
		"order_returned",
		"order_updated",
		"product_updated",
		"inventory_changed",
		"collection_updated",
		"page_updated",
		"menu_updated",
	)
}


doc_events = {
	"Website Settings": {
		"validate": "commera.localization.redirect_rules.canonicalize_redirect_targets",
	},
	"User": {
		"before_insert": "commera.utils.prevent_welcome_email",
	},
	"Item Group": {
		"before_validate": "commera.utils.set_item_group_displayname",
		"on_update": "commera.plugin_events.on_item_group_change",
		"on_trash": "commera.plugin_events.on_item_group_change",
	},
	"Shop Web Page": {
		"on_update": "commera.plugin_events.on_shop_web_page_change",
		"on_trash": [
			"commera.plugin_events.on_shop_web_page_change",
			"commera.localization.content.delete_translations",
		],
	},
	"Footer Section Config": {
		"on_update": "commera.plugin_events.on_menu_change",
		"on_trash": "commera.localization.content.delete_translations",
	},
	"Commera Settings": {"on_update": "commera.plugin_events.on_menu_change"},
	"Price List": {
		"validate": "commera.doc_events.price_list.validate",
	},
	"Gateway Payment Request": {
		"on_update": "commera.api.payment_hooks.on_payment_request_update",
	},
	"Quotation": {
		"before_validate": "commera.discounts.pricing.remove_code_discounts",
		"validate": "commera.discounts.pricing.apply_code_discounts",
	},
	"Sales Order": {
		"before_insert": "commera.discounts.pricing.drop_copied_discounts",
		"before_validate": "commera.discounts.pricing.remove_code_discounts",
		"validate": "commera.discounts.pricing.apply_code_discounts",
		"after_insert": [
			"commera.discounts.usage.record_discount_uses",
			"commera.jobs.send_order_success_acknowledgement",
		],
		"on_submit": [
			"commera.jobs.send_order_success_acknowledgement",
			"commera.utils.update_so_status_from_related_doc",
			"commera.plugin_events.on_sales_order_stock_reservation",
		],
		"on_cancel": [
			"commera.jobs.send_order_cancel_acknowledgement",
			"commera.utils.update_so_status_from_related_doc",
			"commera.plugin_events.on_sales_order_cancel",
			"commera.plugin_events.on_sales_order_stock_reservation",
		],
		"on_update_after_submit": "commera.plugin_events.on_sales_order_update_after_submit",
		"on_trash": "commera.doc_events.sales_order.on_trash",
	},
	"Stock Ledger Entry": {
		"after_insert": [
			"commera.jobs.send_product_back_in_stock_email",
			"commera.plugin_events.on_stock_ledger_entry_insert",
		]
	},
	"Item": {"on_update": "commera.plugin_events.on_item_update"},
	"Item Price": {
		"on_update": "commera.plugin_events.on_item_price_change",
		"on_trash": "commera.plugin_events.on_item_price_change",
	},
	"Style Attribute Variant": {
		"on_update": [
			"commera.search.sync.on_update",
			"commera.plugin_events.on_style_attribute_variant_update",
		],
		"after_rename": "commera.search.sync.after_rename",
		"on_trash": [
			"commera.search.sync.on_trash",
			"commera.plugin_events.on_style_attribute_variant_trash",
			"commera.localization.content.delete_translations",
		],
	},
	"Content Translation": {
		"on_update": "commera.search.translations.on_translation_change",
		"on_trash": "commera.search.translations.on_translation_change",
	},
	"Ecommerce Category": {
		"on_update": ["commera.search.sync.on_update", "commera.plugin_events.on_menu_change"],
		"after_rename": "commera.search.sync.after_rename",
		"on_trash": [
			"commera.search.sync.on_trash",
			"commera.plugin_events.on_menu_change",
			"commera.localization.content.delete_translations",
		],
	},
	"Sales Invoice": {
		"before_validate": "commera.discounts.pricing.remove_code_discounts",
		"validate": "commera.discounts.pricing.apply_code_discounts",
		"on_submit": "commera.utils.update_so_status_from_related_doc",
	},
	"Payment Entry": {"on_submit": "commera.plugin_events.on_payment_entry_submit"},
	"Delivery Note": {
		"before_validate": "commera.discounts.pricing.remove_code_discounts",
		"validate": "commera.discounts.pricing.apply_code_discounts",
		"after_insert": "commera.utils.update_so_status_from_related_doc",
		"on_submit": "commera.utils.update_so_status_from_related_doc",
		"on_cancel": "commera.utils.update_so_status_from_related_doc",
		"on_trash": "commera.utils.update_so_status_from_related_doc",
	},
	"Shipment": {
		"validate": "commera.doc_events.shipment.validate",
		"before_update_after_submit": "commera.doc_events.shipment.before_update_after_submit",
		"on_update": "commera.doc_events.shipment.on_update",
		"on_submit": "commera.doc_events.shipment.on_submit",
		"on_update_after_submit": "commera.doc_events.shipment.on_update_after_submit",
		"before_cancel": "commera.doc_events.shipment.before_cancel",
		"on_cancel": "commera.doc_events.shipment.on_cancel",
	},
}

jinja = {
	"filters": ["commera.utils.can_return"],
	"methods": [
		"commera.branding.get_brand_assets",
		"commera.guest.is_guest_checkout_enabled",
		"commera.localization.get_localization",
		"commera.localization.switch_url",
		"commera.localization.url",
		"commera.utils.format_theme_css",
		"commera.utils.get_currency_symbol",
		"commera.search.result_card.get_search_result_fields",
		"commera.search.typeahead.get_typeahead",
		"commera.sdk.format.product_url",
		"commera.seo_jinja",
		"commera.shop_data.get_header_data",
		"commera.shop_data.get_storefront_menu",
		"commera.store_frame.get_shop_details",
		"commera.store_frame.get_storefront_footer",
		"commera.shop_themes.jinja_helpers.shop_theme_asset_url",
		"commera.shop_themes.jinja_helpers.shop_theme_config",
		"commera.shop_themes.jinja_helpers.format_shop_theme_css",
		"commera.shop_themes.sections.render_layout",
		"commera.storefront_plugins.format_plugin_includes",
		"commera.storefront_plugins.plugin_slot",
	],
}

update_website_context = [
	"commera.website_context.update_website_context",
	"commera.roles.redirect_commera_users_from_desk",
	"commera.onboarding.redirect_owner_from_desk",
]

# GDPR erasure: the event log stores the signed-in email as plain Data, so core is told which column to redact.
user_data_fields = [
	{
		"doctype": "Storefront Analytics Event",
		"filter_by": "visitor_user",
		"redact_fields": ["visitor_user"],
	},
]

# Deliberately NOT frappe's `sqlite_search` hook: it enlists a global `*` doc_events probe on every save.


ignore_links_on_delete = [
	"Bulk Image Upload Log",
	"Bulk Style Attribute Configurator Creation Log",
	"Commera Event",
	"Commera Event Delivery",
	"Commera Webhook Log",
	# A use is never given back, so its row outlives a deleted order.
	"Commera Discount Use",
	# Lets a record go even when its app does not hook delete_translations on on_trash.
	"Content Translation",
]

# Apps
# ------------------


# `name` must stay the app name: frappe.apps.get_route matches on it to resolve /apps tiles.
add_to_apps_screen = [
	{
		"name": "commera",
		"logo": "/assets/commera/images/commera.svg",
		"title": "Commera",
		"route": "/commera",
		"has_permission": "commera.api.permission.has_app_permission",
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/commera/css/commera.css"
# app_include_js = "/assets/commera/js/commera.js"

# include js, css files in header of web template
# web_include_css = "/assets/commera/css/commera.css"
# web_include_js = "/assets/commera/js/commera.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "commera/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "commera/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "commera.utils.jinja_methods",
# 	"filters": "commera.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "commera.install.before_install"
# after_install = "commera.install.after_install"

# Uninstallation
# ------------

# after_uninstall = "commera.uninstall.after_uninstall"

# Integration Setup
# ------------------

# before_app_install = "commera.utils.before_app_install"
# after_app_install = "commera.utils.after_app_install"

# Integration Cleanup
# -------------------

# before_app_uninstall = "commera.utils.before_app_uninstall"
# after_app_uninstall = "commera.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "commera.notifications.get_notification_config"

# Permissions
# -----------

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes


# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"commera.tasks.all"
# 	],
# 	"daily": [
# 		"commera.tasks.daily"
# 	],
# 	"hourly": [
# 		"commera.tasks.hourly"
# 	],
# 	"weekly": [
# 		"commera.tasks.weekly"
# 	],
# 	"monthly": [
# 		"commera.tasks.monthly"
# 	],
# }

# Testing
# -------

before_tests = "commera.install.before_tests"

# Overriding Methods
# ------------------------------

override_whitelisted_methods = {
	# Carriers set up before the move still post to the bwh_shipping URL; drop once they use the new one.
	"bwh_shipping.bwh_shipping.webhook.handle": "commera.shipping.webhook.handle",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "commera.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------

# after_request = ["commera.utils.after_request"]

# Job Events
# ----------
# before_job = ["commera.utils.before_job"]
# after_job = ["commera.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Automatically update python controller files with type annotations for this app.
export_python_type_annotations = True

default_log_clearing_doctypes = {"Commera Event": 14, "Commera Webhook Log": 30}

fixtures = [
	{
		"dt": "Email Template",
		"filters": [
			[
				"name",
				"in",
				("Order Confirmation", "Order Cancellation", "Item In Stock"),
			]
		],
	},
]

scheduler_events = {
	# Cron entries still only fire on the scheduler tick (scheduler_tick_interval, 4 minutes by default),
	# so a retry due after 1 minute really runs up to a tick later.
	"cron": {
		"* * * * *": ["commera.plugin_events.run_due_deliveries"],
	},
	"hourly": [
		"commera.plugin_events.sweep_missed_cod_payments",
		"commera.cloud.link.queue_link_if_pending",
	],
	# Long queue, not the short one: sync_status() is a gateway round-trip per pending request, so a
	# slow gateway would otherwise sit on a worker the whole storefront shares.
	"hourly_long": [
		"commera.jobs.sync_pending_gateway_payments",
	],
	"daily": [
		"commera.jobs.delete_notified_oos",
		"commera.jobs.delete_old_draft_quotations",
		"commera.commera_ecommerce.doctype.commera_cart.commera_cart.delete_abandoned_guest_carts",
		"commera.search.build.rebuild_index_nightly",
		"commera.og.generator.clear_old_cards",
	],
}
