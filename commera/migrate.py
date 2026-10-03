import traceback

import frappe
from bwh_payments.bwh_payments.utils import get_available_payment_modes
from frappe.model.sync import sync_for

from commera.api.payments import COD_PAYMENT_MODE
from commera.commera_ecommerce.doctype.commera_settings.navbar.navbar_manager import (
	seed_menu_when_empty,
)
from commera.search.build import ensure_index_built
from commera.search.record_builder import DEFAULT_CONTENT_FIELDS
from commera.search.result_card import DEFAULT_RESULT_FIELDS, RESULT_CARD_CATALOG
from commera.shop_themes.doctype.shop_theme_settings.shop_theme_settings import seed_default_routes
from commera.www.llms import DEFAULT_LLMS_TXT

# Sentinel marking the robots.txt value as ours; absent from a non-blank value, an admin owns it.
ROBOTS_MARKER = "# managed by commera"


def after_install():
	# install_app syncs before commera is in installed_apps, so our importable_doctypes hook is skipped.
	sync_for("commera")
	create_payment_modes()
	try:
		create_default_email_templates()
		assign_default_email_templates()
	except Exception as e:
		import traceback

		error_msg = f"Error creating default email templates: {e!s}"
		frappe.log_error(traceback.format_exc(), "Commera Installation - Email Templates")
		frappe.errprint(error_msg)
		frappe.errprint(traceback.format_exc())

	register_optional_doctype_links()
	populate_search_settings()
	ensure_storefront_search_index()
	setup_robots_txt()
	seed_llms_txt()
	seed_default_routes()
	activate_summer_theme()
	seed_menu_when_empty()


def activate_summer_theme():
	settings = frappe.get_doc("Shop Theme Settings")
	settings.active_theme = "Summer Theme"
	settings.dynamic_pages_enabled = 1
	settings.save(ignore_permissions=True)


def after_migrate():
	create_payment_modes()
	register_optional_doctype_links()
	populate_search_settings()
	ensure_storefront_search_index()
	setup_robots_txt()
	seed_llms_txt()
	seed_default_routes()


def populate_search_settings():
	"""Seed the search content/result field tables when they have never been configured (idempotent)."""
	if not frappe.db.exists("DocType", "Commera Settings"):
		return

	settings = frappe.get_single("Commera Settings")
	if settings.search_content_fields and settings.search_result_fields:
		return

	if not settings.search_content_fields:
		for search_doctype, field in DEFAULT_CONTENT_FIELDS:
			settings.append("search_content_fields", {"search_doctype": search_doctype, "field": field})

	if not settings.search_result_fields:
		for field in RESULT_CARD_CATALOG:
			settings.append(
				"search_result_fields",
				{"field": field, "show": 1 if field in DEFAULT_RESULT_FIELDS else 0},
			)

	# Fresh site: company/price lists are unset, so ignore_mandatory stops save() raising MandatoryError.
	settings.flags.ignore_mandatory = True
	settings.save(ignore_permissions=True)


def ensure_storefront_search_index():
	"""Backstop the storefront search index on install/migrate; never fail migrate over it."""
	try:
		ensure_index_built()
	except Exception:
		frappe.log_error(traceback.format_exc(), "Storefront Search Index - ensure_index_built")


def register_optional_doctype_links():
	"""Add Customize Form connections for optional integrations whose doctypes come from tabby_frappe."""
	add_sales_order_link_if_doctype_exists("Tabby Payment Request", "ref_docname")


def add_sales_order_link_if_doctype_exists(link_doctype: str, link_fieldname: str):
	if not frappe.db.exists("DocType", link_doctype):
		return

	customize_form = frappe.get_doc({"doctype": "Customize Form", "doc_type": "Sales Order"})
	customize_form.run_method("fetch_to_customize")
	if any(row.link_doctype == link_doctype for row in (customize_form.get("links") or [])):
		return

	customize_form.append(
		"links",
		{
			"link_doctype": link_doctype,
			"link_fieldname": link_fieldname,
		},
	)
	try:
		customize_form.save()
	except Exception:
		import traceback

		frappe.log_error(traceback.format_exc(), f"commera: optional link for {link_doctype}")


def create_payment_modes():
	"""Every gateway needs a Mode of Payment of the same name for its Payment Entries to post."""
	payment_modes = dict.fromkeys(get_available_payment_modes(), "Bank")
	payment_modes[COD_PAYMENT_MODE] = "Cash"
	for mode_of_payment, payment_type in payment_modes.items():
		add_payment_mode(mode_of_payment, payment_type)


def add_payment_mode(mode_of_payment: str, payment_type: str):
	if not frappe.db.exists("Mode of Payment", mode_of_payment):
		frappe.get_doc(
			{
				"doctype": "Mode of Payment",
				"mode_of_payment": mode_of_payment,
				"enabled": True,
				"type": payment_type,
			}
		).insert(ignore_if_duplicate=True)

	# ERPNext refuses a Payment Entry for a Mode of Payment with no account for the company.
	company = get_shop_company()
	default_cash_account = company and frappe.get_cached_value("Company", company, "default_cash_account")
	if not default_cash_account:
		return

	payment_mode = frappe.get_doc("Mode of Payment", mode_of_payment)
	if any(row.company == company for row in payment_mode.accounts):
		return
	payment_mode.append("accounts", {"company": company, "default_account": default_cash_account})
	payment_mode.save(ignore_permissions=True)


def get_shop_company() -> str | None:
	return frappe.db.get_single_value("Commera Settings", "company") or frappe.get_cached_value(
		"Global Defaults", "Global Defaults", "default_company"
	)


DEFAULT_EMAIL_TEMPLATES = {
	"order_confirmation_email_template": "Order Confirmation",
	"order_cancellation_email_template": "Order Cancellation",
	"item_in_stock_email_template": "Item In Stock",
}


def assign_default_email_templates():
	# The fields are mandatory, so while any is empty every save of Commera Settings fails, even one
	# that only changes the company. set_single_value skips that check, which a save() here cannot.
	for fieldname, template in DEFAULT_EMAIL_TEMPLATES.items():
		if frappe.db.get_single_value("Commera Settings", fieldname):
			continue
		if frappe.db.exists("Email Template", template):
			frappe.db.set_single_value("Commera Settings", fieldname, template)


def create_default_email_templates():
	"""Create default email templates required by Commera Settings"""

	email_templates = [
		{
			"name": "Order Confirmation",
			"subject": "Order Confirmation - {{ doc.name }}",
			"response": """Dear {{ doc.customer_name }},

Thank you for your order! Your order has been confirmed.

Order Details:
Order ID: {{ doc.name }}
Date: {{ doc.transaction_date }}
Total: {{ doc.grand_total }}

You can track your order status at: {{ login_url }}

Best regards,
{{ company }}""",
			"doctype": "Sales Order",
		},
		{
			"name": "Item In Stock",
			"subject": "Item Back in Stock - {{ item.item_name }}",
			"response": """Dear Customer,

Great news! The item "{{ item.item_name }}" is now back in stock.

You can purchase it now at: {{ item_url }}

Best regards,
{{ company }}""",
			"doctype": "Item",
		},
		{
			"name": "Order Cancellation",
			"subject": "Order Cancellation Confirmation - {{ doc.name }}",
			"response": """Dear {{ doc.customer_name }},

Your order {{ doc.name }} has been cancelled as requested.

If you have any questions, please contact our customer service.

Best regards,
{{ company }}""",
			"doctype": "Sales Order",
		},
	]

	for template_data in email_templates:
		if not frappe.db.exists("Email Template", template_data["name"]):
			template = frappe.get_doc({"doctype": "Email Template", **template_data})
			template.insert(ignore_permissions=True)
			frappe.errprint(f"Created Email Template: {template_data['name']}")
		else:
			frappe.errprint(f"Email Template '{template_data['name']}' already exists")


def seed_llms_txt():
	current = frappe.db.get_single_value("Commera Settings", "llms_txt")
	if not (current and current.strip()):
		frappe.db.set_single_value("Commera Settings", "llms_txt", DEFAULT_LLMS_TXT)


def setup_robots_txt():
	# Core's frappe/www/robots.py serves this value, so we only write it.
	current = frappe.db.get_single_value("Website Settings", "robots_txt") or ""
	if current.strip() and ROBOTS_MARKER not in current:
		return

	site_url = frappe.utils.get_url().rstrip("/")
	robots_txt = (
		f"{ROBOTS_MARKER}\n"
		"User-agent: *\n"
		"Allow: /\n"
		"Disallow: /app\n"
		"Disallow: /api\n"
		"Disallow: /private\n"
		# Faceted/sorted/paged listings are duplicate surfaces: they burn crawl budget and dilute signals.
		"Disallow: /*?search=\n"
		"Disallow: /*?sort=\n"
		"Disallow: /*?page=\n"
		"Disallow: /*?filter=\n"
		# Disallow is a prefix match: the explicit checkout line is redundant but kept deliberately.
		"Disallow: /en/cart\n"
		"Disallow: /ar/cart\n"
		"Disallow: /en/cart/checkout\n"
		"Disallow: /en/account\n"
		"Disallow: /ar/account\n\n"
		f"Sitemap: {site_url}/sitemap.xml\n"
	)
	frappe.db.set_single_value("Website Settings", "robots_txt", robots_txt)
