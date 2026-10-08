app_name = "commera"
app_title = "Commera"
app_publisher = "hussain@buildwithhussain.com"
app_description = "Ecommerce extension for ERPNext"
app_email = "rahul@buildwithhussain.com"
app_license = "agpl-3.0"

# frappe/payments deliberately absent: bwh_payments ships its own Payment Gateway Profile and base_class.
required_apps = ["frappe/erpnext", "bwhtech/bwh_payments", "bwhtech/bwh_shipping"]


website_redirects = [
	{"source": "/products", "target": "/en/products"},
	{"source": "/products/(.*)", "target": r"/en/products/\1"},
	{"source": "/", "target": "/en"},
	{"source": "/cart", "target": "/en/cart"},
	{"source": "/cart/checkout", "target": "/en/cart/checkout"},
	{"source": "/account", "target": "en/account/dashboard"},
	{"source": "/account/(.*)", "target": r"/en/account/\1"},
	{"source": "/en/account", "target": "/account/dashboard"},
	{"source": "/ar/account", "target": "/account/dashboard"},
	{"source": "/en-US/(.*)", "target": r"/en/\1"},
	{"source": "/en-GB/(.*)", "target": r"/en/\1"},
]

# website_path_resolver = "commera.utils.resolve_bilingual_path"

website_route_rules = [
	# SPA client-side routing: every /commera deep link resolves to the same shell so a reload does not 404.
	{"from_route": "/commera/<path:app_path>", "to_route": "/commera"},
	# ------------
	# English Routes
	# ------------
	#
	# -> Landing
	{"from_route": "/en", "to_route": "/index.html"},
	# -> Products
	{"from_route": "/en/products", "to_route": "/products/list.html"},
	{"from_route": "/en/products/<path:route>", "to_route": "/products/details.html"},
	# -> Cart / Checkout
	{"from_route": "/en/cart", "to_route": "/cart/cart.html"},
	{"from_route": "/en/cart/checkout", "to_route": "/cart/checkout.html"},
	# -> Account
	{"from_route": "/en/account/dashboard", "to_route": "/account/dashboard.html"},
	{"from_route": "/en/account/profile", "to_route": "/account/profile.html"},
	{"from_route": "/en/account/orders", "to_route": "/account/orders/index.html"},
	{
		"from_route": "/en/account/orders/confirmation",
		"to_route": "/account/orders/confirmation.html",
	},
	{
		"from_route": "/en/account/orders/detail",
		"to_route": "/account/orders/detail.html",
	},
	{"from_route": "/en/account/wishlist", "to_route": "/account/wishlist.html"},
	{"from_route": "/en/account/address", "to_route": "/account/address.html"},
	#
	# ------------
	# Arabic Routes
	# ------------
	#
	# -> Landing
	{"from_route": "/ar", "to_route": "/index.html"},
	# -> Products
	{"from_route": "/ar/products", "to_route": "/products/list.html"},
	{"from_route": "/ar/products/<path:route>", "to_route": "/products/details.html"},
	# -> Cart / Checkout
	{"from_route": "/ar/cart", "to_route": "/cart/cart.html"},
	{"from_route": "/ar/cart/checkout", "to_route": "/cart/checkout.html"},
	# -> Account
	{"from_route": "/ar/account/dashboard", "to_route": "/account/dashboard.html"},
	{"from_route": "/ar/account/profile", "to_route": "/account/profile.html"},
	{"from_route": "/ar/account/orders", "to_route": "/account/orders/index.html"},
	{
		"from_route": "/ar/account/orders/confirmation",
		"to_route": "/account/orders/confirmation.html",
	},
	{
		"from_route": "/ar/account/orders/detail",
		"to_route": "/account/orders/detail.html",
	},
	{"from_route": "/ar/account/wishlist", "to_route": "/account/wishlist.html"},
	{"from_route": "/ar/account/address", "to_route": "/account/address.html"},
	# ------------
	# Crawl infrastructure (language-agnostic)
	# ------------
	{"from_route": "/sitemap-<seg_type>-<page>.xml", "to_route": "sitemap_segment.xml"},
	{"from_route": "/og-image/<path:route>", "to_route": "/og_image_render"},
]

before_request = ["commera.utils.before_request"]

# Runs before every core renderer (frappe/website/path_resolver.py); can_render() opts out when no theme.
page_renderer = ["commera.shop_themes.theme_resolver.ThemePageRenderer"]

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
	"Style Attribute Variant": "public/js/extends/seo_listing.js",
	"Ecommerce Category": "public/js/extends/seo_listing.js",
	"Commera Settings": [
		"public/js/extends/seo_listing.js",
		"public/js/extends/footer_manager.js",
		"public/js/extends/navbar_manager.js",
	],
}

after_install = "commera.migrate.after_install"
after_migrate = "commera.migrate.after_migrate"
after_app_install = "commera.storefront_plugins.sync_storefront_apps"
setup_wizard_complete = "commera.swatches.drop_unused_colour_attribute"


doc_events = {
	"User": {
		"before_insert": "commera.utils.prevent_welcome_email",
	},
	"Item Group": {
		"before_validate": "commera.utils.set_item_group_displayname",
	},
	"Gateway Payment Request": {
		"on_update": "commera.api.payment_hooks.on_payment_request_update",
	},
	"Sales Order": {
		"after_insert": "commera.jobs.send_order_success_acknowledgement",
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
		"on_trash": "commera.search.sync.on_trash",
	},
	"Ecommerce Category": {
		"on_update": "commera.search.sync.on_update",
		"after_rename": "commera.search.sync.after_rename",
		"on_trash": "commera.search.sync.on_trash",
	},
	"Sales Invoice": {"on_submit": "commera.utils.update_so_status_from_related_doc"},
	"Payment Entry": {"on_submit": "commera.plugin_events.on_payment_entry_submit"},
	"Delivery Note": {
		"after_insert": "commera.utils.update_so_status_from_related_doc",
		"on_submit": "commera.utils.update_so_status_from_related_doc",
		"on_cancel": "commera.utils.update_so_status_from_related_doc",
		"on_trash": "commera.utils.update_so_status_from_related_doc",
	},
	"Shipping Request": {"on_update": "commera.utils.update_so_status_from_related_doc"},
}

jinja = {
	"filters": ["commera.utils.can_return"],
	"methods": [
		"commera.branding.get_brand_assets",
		"commera.guest.is_guest_checkout_enabled",
		"commera.utils.format_theme_css",
		"commera.utils.get_currency_symbol",
		"commera.search.result_card.get_search_result_fields",
		"commera.seo_jinja",
		"commera.shop_data.get_header_data",
		"commera.shop_data.get_storefront_menu",
		"commera.shop_themes.jinja_helpers.shop_theme_asset_url",
		"commera.shop_themes.jinja_helpers.shop_theme_config",
		"commera.storefront_plugins.format_plugin_includes",
		"commera.storefront_plugins.plugin_slot",
	],
}

update_website_context = "commera.website_context.update_website_context"

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

# before_uninstall = "commera.uninstall.before_uninstall"
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
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "commera.event.get_events"
# }
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

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"commera.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
export_python_type_annotations = True

default_log_clearing_doctypes = {"Commera Event": 14}

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
	],
	# Long queue, not the short one: sync_status() is a gateway round-trip per pending request, so a
	# slow gateway would otherwise sit on a worker the whole storefront shares.
	"hourly_long": [
		"commera.jobs.sync_pending_gateway_payments",
	],
	"daily": [
		"commera.jobs.delete_notified_oos",
		"commera.jobs.delete_old_draft_quotations",
		"commera.search.build.rebuild_index_nightly",
		"commera.og.generator.clear_old_cards",
	],
}
