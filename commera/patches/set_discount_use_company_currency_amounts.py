import frappe
from frappe.utils.data import flt

from commera.discounts.usage import refresh_usage


def execute():
	"""Discount given, sales and budgets add up uses in the company currency, at each order's exchange rate."""
	uses = frappe.get_all(
		"Commera Discount Use", fields=["name", "discount", "sales_order", "amount", "order_total"]
	)
	conversion_rates = (
		dict(
			frappe.get_all(
				"Sales Order",
				filters={"name": ["in", list({use.sales_order for use in uses})]},
				fields=["name", "conversion_rate"],
				as_list=True,
			)
		)
		if uses
		else {}
	)
	for use in uses:
		conversion_rate = flt(conversion_rates.get(use.sales_order)) or 1
		frappe.db.set_value(
			"Commera Discount Use",
			use.name,
			{
				"base_amount": flt(flt(use.amount) * conversion_rate, 2),
				"base_order_total": flt(flt(use.order_total) * conversion_rate, 2),
			},
			update_modified=False,
		)
	refresh_usage({use.discount for use in uses}, set())
