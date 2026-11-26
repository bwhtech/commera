import erpnext
import frappe
from erpnext.setup.utils import get_exchange_rate
from frappe.utils.data import flt

from commera.cart_prices import apply_market, price_regular_lines
from commera.core import system_user_session
from commera.discounts.pricing import apply_code_discounts
from commera.item_price_guard import skip_auto_item_price
from commera.localization.market_prices import MarketPrices


def has_active_pricing_rules() -> bool:
	"""Whether any enabled selling ERPNext Pricing Rule exists."""
	return bool(frappe.db.get_value("Pricing Rule", {"disable": 0, "selling": 1}, "name"))


def has_any_item_taxes() -> bool:
	"""Whether any Item Tax child row exists on this site."""
	return bool(frappe.db.exists("Item Tax", {}))


def can_fast_price_preview(item_codes: list[str]) -> bool:
	if has_active_pricing_rules():
		return False
	if not has_any_item_taxes():
		return True
	unique_codes = list(dict.fromkeys(item_codes))
	if not unique_codes:
		return True
	if frappe.db.exists("Item Tax", {"parenttype": "Item", "parent": ("in", unique_codes)}):
		return False
	groups = list({g for code in unique_codes if (g := frappe.get_cached_value("Item", code, "item_group"))})
	if groups and frappe.db.exists("Item Tax", {"parenttype": "Item Group", "parent": ("in", groups)}):
		return False
	return True


def populate_fast_preview_fields(quotation, prices: MarketPrices):
	"""Populate the fields calculate_taxes_and_totals and apply_code_discounts need using cached metadata,
	avoiding ERPNext's heavyweight set_missing_values (Customer child tables, Bin, Product Bundle, Item Price)."""
	company_currency = erpnext.get_company_currency(quotation.company)
	quotation.price_list_currency = (
		frappe.get_cached_value("Price List", prices.sale_price_list, "currency") or prices.currency
	)
	if quotation.currency == company_currency:
		quotation.conversion_rate = 1.0
	else:
		quotation.conversion_rate = (
			flt(
				get_exchange_rate(
					quotation.currency, company_currency, quotation.transaction_date, "for_selling"
				)
			)
			or 1.0
		)
	if quotation.price_list_currency == company_currency:
		quotation.plc_conversion_rate = 1.0
	elif quotation.price_list_currency == quotation.currency:
		quotation.plc_conversion_rate = quotation.conversion_rate
	else:
		quotation.plc_conversion_rate = (
			flt(
				get_exchange_rate(
					quotation.price_list_currency, company_currency, quotation.transaction_date, "for_selling"
				)
			)
			or 1.0
		)

	if quotation.party_name:
		cust = frappe.get_cached_value(
			"Customer", quotation.party_name, ["customer_name", "customer_group", "territory"], as_dict=True
		)
		if cust:
			quotation.customer_name = cust.customer_name
			quotation.customer_group = cust.customer_group
			quotation.territory = cust.territory

	for item in quotation.items:
		meta = frappe.get_cached_value(
			"Item",
			item.item_code,
			["item_name", "item_group", "brand", "stock_uom", "sales_uom", "description"],
			as_dict=True,
		)
		if meta:
			item.item_name = meta.item_name
			item.item_group = meta.item_group
			item.brand = meta.brand
			item.stock_uom = meta.stock_uom
			item.uom = meta.sales_uom or meta.stock_uom
			item.description = meta.description or meta.item_name
		if item.uom and item.stock_uom and item.uom != item.stock_uom:
			from erpnext.stock.get_item_details import get_conversion_factor

			item.conversion_factor = flt(get_conversion_factor(item.item_code, item.uom)["conversion_factor"])
		else:
			item.conversion_factor = 1.0
		item.price_list_rate = flt(item.price_list_rate)
		item.discount_percentage = 0.0
		item.discount_amount = 0.0
		item.rate = item.price_list_rate
		item.item_tax_rate = "{}"
		item.stock_qty = flt(item.qty) * flt(item.conversion_factor)
		item.amount = flt(item.qty) * flt(item.rate)
		item.net_rate = item.rate
		item.net_amount = item.amount
		item.base_price_list_rate = flt(item.price_list_rate) * flt(quotation.plc_conversion_rate)
		item.base_rate = flt(item.rate) * flt(quotation.conversion_rate)
		item.base_amount = flt(item.amount) * flt(quotation.conversion_rate)
		item.base_net_rate = item.base_rate
		item.base_net_amount = item.base_amount

	if not quotation.taxes:
		total = sum(flt(i.amount) for i in quotation.items)
		base_total = sum(flt(i.base_amount) for i in quotation.items)
		quotation.total_qty = sum(flt(i.qty) for i in quotation.items)
		quotation.total = total
		quotation.net_total = total
		quotation.base_total = base_total
		quotation.base_net_total = base_total
		quotation.grand_total = total
		quotation.base_grand_total = base_total
		quotation.rounded_total = total
		quotation.base_rounded_total = base_total


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
			"custom_discount_codes": codes,
			"party_name": frappe.db.get_value("Portal User", {"user": user}, "parent") if user else None,
			"contact_email": user,
		}
	)
	quotation.update(fields or {})
	quotation.flags.update(flags or {})
	apply_market(quotation, prices)
	for line in lines:
		quotation.append(
			"items",
			{"item_code": line["item_code"], "qty": line["qty"], "warehouse": settings.ecommerce_warehouse},
		)
	use_fast_path = can_fast_price_preview([line["item_code"] for line in lines])
	price_regular_lines(quotation, prices, set_all_prices=use_fast_path)
	with system_user_session(), skip_auto_item_price():
		if use_fast_path:
			populate_fast_preview_fields(quotation, prices)
			if quotation.taxes:
				quotation.calculate_taxes_and_totals()
		else:
			quotation.run_method("set_missing_values")
			quotation.calculate_taxes_and_totals()
		quotation.flags._commera_totals_calculated = bool(not use_fast_path or quotation.taxes)
		apply_code_discounts(quotation)
		if use_fast_path and not quotation.flags.get("_commera_totals_calculated"):
			quotation.calculate_taxes_and_totals()
	return quotation
