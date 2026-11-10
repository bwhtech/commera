import frappe

from commera.cart_prices import price_regular_lines
from commera.core import system_user_session
from commera.discounts.pricing import apply_code_discounts
from commera.localization.market_prices import MarketPrices


def get_preview_quotation(
	lines: list[dict],
	codes: str | None = None,
	user: str | None = None,
	flags=None,
	fields: dict | None = None,
):
	# Elevated, like checkout: ERPNext reads Items the shopper cannot.
	settings = frappe.get_cached_doc("Commera Settings")
	prices = MarketPrices.current()
	quotation = frappe.new_doc("Quotation")
	quotation.update(
		{
			"quotation_to": "Customer",
			"company": settings.get("company") or frappe.defaults.get_global_default("company"),
			"order_type": "Shopping Cart",
			"selling_price_list": prices.sale_price_list,
			"currency": prices.currency,
			"custom_discount_codes": codes,
			"party_name": user and frappe.db.get_value("Portal User", {"user": user}, "parent"),
			"contact_email": user,
		}
	)
	quotation.update(fields or {})
	quotation.flags.update(flags or {})
	for line in lines:
		quotation.append(
			"items",
			{"item_code": line["item_code"], "qty": line["qty"], "warehouse": settings.ecommerce_warehouse},
		)
	price_regular_lines(quotation, prices)
	with system_user_session():
		quotation.run_method("set_missing_values")
		quotation.calculate_taxes_and_totals()
		apply_code_discounts(quotation)
	return quotation
