# Copyright (c) 2026, company@bwhstudios.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.translate import print_language
from frappe.utils import get_url
from frappe.utils.data import cint, cstr

from commera.core import OTP_EXPIRY_SECONDS
from commera.localization import StorefrontLanguages
from commera.notifications import (
	ALWAYS_ON_EMAILS,
	EMAIL_LABELS,
	deliver_customer_email,
	get_back_in_stock_context,
	get_brand_context,
	get_customer_email_setting,
	get_order_context,
	render_customer_email,
)
from commera.sdk import STORE_ORDER_TYPE

SETTINGS_DOCTYPE = "Commera Settings"
SAMPLE_SIGN_IN_CODE = "482913"
TEMPLATE_OPTION_LIMIT = 100


@frappe.whitelist()
def get_customer_emails() -> list[dict]:
	frappe.has_permission(SETTINGS_DOCTYPE, ptype="read", throw=True)
	settings = frappe.get_cached_doc(SETTINGS_DOCTYPE)
	return [format_email_row(row) for row in settings.customer_emails]


@frappe.whitelist(methods=["POST"])
def set_email_enabled(email: str, enabled: bool) -> dict:
	settings, row = get_editable_row(email)
	row.enabled = cint(enabled)
	settings.save()
	return format_email_row(row)


@frappe.whitelist(methods=["POST"])
def set_email_template(email: str, email_template: str | None = None) -> dict:
	settings, row = get_editable_row(email)
	row.email_template = cstr(email_template).strip() or None
	settings.save()
	return format_email_row(row)


@frappe.whitelist()
def get_email_template_options(search_text: str | None = None) -> list[dict]:
	frappe.has_permission(SETTINGS_DOCTYPE, ptype="read", throw=True)
	filters = {"name": ("like", f"%{cstr(search_text)}%")} if search_text else {}
	names = frappe.get_list(
		"Email Template", filters=filters, pluck="name", order_by="name asc", limit=TEMPLATE_OPTION_LIMIT
	)
	return [{"label": name, "value": name} for name in names]


@frappe.whitelist()
def get_email_preview(email: str) -> dict:
	frappe.has_permission(SETTINGS_DOCTYPE, ptype="read", throw=True)
	get_email_row(email)
	sales_order = get_preview_order(email)
	if email not in SAMPLE_EMAIL_ARGS and not sales_order:
		return {"subject": None, "html": None, "needs_order": True}
	with print_language(sales_order.language if sales_order else None):
		return {**render_customer_email(email, get_preview_args(email, sales_order)), "needs_order": False}


@frappe.whitelist(methods=["POST"])
def send_test_email(email: str) -> dict:
	frappe.has_permission(SETTINGS_DOCTYPE, ptype="write", throw=True)
	get_email_row(email)
	recipient = frappe.db.get_value("User", frappe.session.user, "email")
	if not recipient:
		frappe.throw(_("Your user has no email address to send the test to."))
	sales_order = get_preview_order(email)
	if email not in SAMPLE_EMAIL_ARGS and not sales_order:
		frappe.throw(_("Place a test order on your store first. This email shows an order."))
	language = sales_order.language if sales_order else None
	with print_language(language):
		deliver_customer_email(email, [recipient], get_preview_args(email, sales_order), language=language)
	return {"recipient": recipient}


def format_email_row(row) -> dict:
	labels = EMAIL_LABELS.get(row.email) or {}
	return {
		"email": row.email,
		"label": str(labels.get("label") or _(frappe.unscrub(row.email))),
		"description": str(labels.get("description") or ""),
		"enabled": bool(row.enabled),
		"email_template": row.email_template,
		"always_on": row.email in ALWAYS_ON_EMAILS,
	}


def get_email_row(email: str):
	row = get_customer_email_setting(email)
	if not row:
		frappe.throw(_("There is no {0} email.").format(email), frappe.DoesNotExistError)
	return row


def get_editable_row(email: str):
	frappe.has_permission(SETTINGS_DOCTYPE, ptype="write", throw=True)
	get_email_row(email)
	settings = frappe.get_doc(SETTINGS_DOCTYPE)
	row = next(row for row in settings.customer_emails if row.email == email)
	return settings, row


def get_preview_order(email: str):
	if email in SAMPLE_EMAIL_ARGS:
		return None
	names = frappe.get_list(
		"Sales Order",
		filters={"order_type": STORE_ORDER_TYPE},
		pluck="name",
		order_by="creation desc",
		limit=1,
	)
	return frappe.get_doc("Sales Order", names[0]) if names else None


def get_preview_args(email: str, sales_order) -> dict:
	args = SAMPLE_EMAIL_ARGS[email]() if email in SAMPLE_EMAIL_ARGS else get_order_context(sales_order)
	return {**args, "language": frappe.local.lang}


def get_sign_in_code_args() -> dict:
	brand = get_brand_context()
	return {
		"brand": brand,
		"store_name": brand["name"],
		"code": SAMPLE_SIGN_IN_CODE,
		"expires_in_minutes": OTP_EXPIRY_SECONDS // 60,
	}


def get_back_in_stock_args() -> dict:
	first_name = frappe.db.get_value("User", frappe.session.user, "first_name")
	product = get_sample_product()
	if product:
		item_code, style_attribute_variant = product
		return {
			**get_back_in_stock_context(item_code, style_attribute_variant),
			"first_name": first_name,
			"product_url": get_url(
				f"/{StorefrontLanguages.load().default.code.lower()}/products/{style_attribute_variant.route}"
			),
		}
	brand = get_brand_context()
	return {
		"brand": brand,
		"store_name": brand["name"],
		"item_name": _("Sample product"),
		"currency": None,
		"product": {"item_name": _("Sample product"), "variant": None, "price": None, "image": None},
		"first_name": first_name,
		"product_url": get_url(),
	}


def get_sample_product():
	variants = frappe.get_all(
		"Style Attribute Variant",
		filters={"is_published": 1},
		fields=["name", "route", "display_name"],
		order_by="modified desc",
		limit=1,
	)
	if not variants:
		return None
	item_codes = frappe.get_all(
		"Color Size Item",
		filters={"parenttype": "Style Attribute Variant", "parent": variants[0].name},
		pluck="item_code",
		order_by="idx asc",
		limit=1,
	)
	return (item_codes[0], variants[0]) if item_codes else None


SAMPLE_EMAIL_ARGS = {
	"sign_in_code": get_sign_in_code_args,
	"back_in_stock": get_back_in_stock_args,
}
