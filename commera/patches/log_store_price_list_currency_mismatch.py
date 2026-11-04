import frappe

from commera.utils import get_store_currency


def execute():
	settings = frappe.get_single("Commera Settings")
	currency = get_store_currency(settings.company)
	for fieldname in ("default_price_list", "sale_price_list"):
		price_list = settings.get(fieldname)
		if not price_list:
			continue
		price_list_currency = frappe.db.get_value("Price List", price_list, "currency")
		if price_list_currency != currency:
			frappe.log_error(
				title=f"Commera Settings: {settings.meta.get_label(fieldname)} is not in the store currency",
				message=(
					f"{price_list} is in {price_list_currency}, but the store sells in {currency}, the currency of "
					f"its company. Prices are compared and charged in {currency}. Pick a price list in {currency} "
					"under Commera Settings."
				),
			)
