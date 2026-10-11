from functools import wraps

import frappe
from erpnext.controllers.website_list_for_contact import get_transaction_list
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.translate import get_all_translations
from frappe.utils import cstr

from commera.search import query as search_query
from commera.utils import get_available_stocks, get_product_list, validate_document_access


def auth_required(func):
	@wraps(func)
	def wrapper(*args, **kwargs):
		current_user = frappe.session.user
		if current_user == "Guest":
			raise frappe.PermissionError
		return func(*args, **kwargs)

	return wrapper


# Only what the screen renders: the whole document carries contact_email, phone and the address block.
ORDER_DETAIL_FIELDS = (
	"name",
	"status",
	"docstatus",
	"transaction_date",
	"delivery_date",
	"currency",
	"net_total",
	"total_taxes_and_charges",
	"grand_total",
	"rounded_total",
)
ORDER_DETAIL_ITEM_FIELDS = ("item_code", "item_name", "qty", "rate", "amount", "image")


# Guests read an order only with its private link key; validate_document_access compares it.
@frappe.whitelist(allow_guest=True)  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=120, seconds=60 * 60)
def get_order_detail(order_name: str, key: str | None = None):
	sales_order = validate_document_access("Sales Order", order_name, key)

	detail = {fieldname: sales_order.get(fieldname) for fieldname in ORDER_DETAIL_FIELDS}
	detail["items"] = [
		{fieldname: item.get(fieldname) for fieldname in ORDER_DETAIL_ITEM_FIELDS}
		for item in sales_order.items
	]
	return {"sales_order": detail}


@frappe.whitelist()
def get_whitelist_transaction_list(
	doctype: str,
	txt: str | None = None,
	filters: dict | None = None,
	limit_start: int | str = 0,
	limit_page_length: int | str = 20,
	order_by: str = "modified",
	custom: bool = False,
):
	return get_transaction_list(doctype, txt, filters, limit_start, limit_page_length, order_by, custom)


# The storefront landing page is public, and so is everything Landing Page Settings holds.
@frappe.whitelist(allow_guest=True)  # nosemgrep: guest-whitelisted-method
def get_homepage_details():
	landing_page = frappe.get_cached_doc("Landing Page Settings")
	landing_page = landing_page.as_dict()
	landing_page["new_arrivals"] = get_item_details(landing_page.get("new_arrivals"))
	landing_page["best_picks"] = get_item_details(landing_page.get("best_picks"))
	landing_page["carousel_1"] = get_item_details(landing_page.get("carousel_1"))
	return landing_page


def get_item_details(items):
	recommended_items = []

	for item in items:
		recommended_website_item = frappe.get_doc("Website Item", {"name": item.get("website_item")})
		recommended_item_context = frappe._dict(
			{"route": recommended_website_item.route or recommended_website_item.make_route()}
		)
		recommended_item_context = recommended_website_item.get_context(recommended_item_context)
		recommended_item_info = {
			"id": recommended_website_item.get("name"),
			"brand": recommended_website_item.get("brand") or recommended_website_item.get("item_group"),
			"product_name": recommended_website_item.get("item_name")
			or recommended_website_item.get("web_item_name"),
			"item_code": recommended_website_item.get("item_code"),
			"has_variants": recommended_website_item.get("has_variants"),
			"description": recommended_website_item.get("description"),
			"website_image": recommended_website_item.get("website_image"),
			"website_image_alt": recommended_website_item.get("website_image_alt"),
			"price_info": recommended_item_context.get("shopping_cart")
			.get("product_info", {})
			.get("price", {}),
		}
		recommended_items.append(recommended_item_info)
	return recommended_items


# Catalogue search is public and rate limited; it returns only published products.
@frappe.whitelist(allow_guest=True)  # nosemgrep: guest-whitelisted-method
@rate_limit(limit=120, seconds=60)
def get_search_results(search: str):
	filters = {"search": cstr(search)}
	if search_query.relevance_sort_available(filters):
		return search_query.storefront_search(filters["search"], limit=6)["products"]
	return get_product_list(filters=filters, page_length=6)


@frappe.whitelist()
def notify_user_product(item: str):
	try:
		user = frappe.session.user

		exists = frappe.db.exists(
			"OOS Notify Subscription",
			{
				"user": user,
				"item": item,
			},
		)
		if exists:
			frappe.db.set_value("OOS Notify Subscription", exists, "notified", 0)
		else:
			frappe.get_doc(
				{
					"doctype": "OOS Notify Subscription",
					"user": user,
					"item": item,
					"notified": 0,
				}
			).insert()
	except Exception:
		frappe.throw(_("Cannot subscribe for notification"))


# UI strings, the same data frappe's own get_boot_translations serves guests.
@frappe.whitelist(allow_guest=True)  # nosemgrep: guest-whitelisted-method
def get_translations(lang: str = "ar"):
	return get_all_translations(lang=lang)


@frappe.whitelist()
def get_stock_for_items(item_codes: list[str] | str):
	frappe.has_permission("Bin", throw=True)

	if isinstance(item_codes, str):
		item_codes = frappe.parse_json(item_codes)

	warehouse = frappe.get_cached_value("Commera Settings", "Commera Settings", "ecommerce_warehouse")
	stocks = get_available_stocks(item_codes, warehouse)
	return {item_code: data["stock_qty"] for item_code, data in stocks.items()}
