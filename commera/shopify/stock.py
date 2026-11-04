import frappe
from frappe import _
from frappe.utils import flt


def get_stock_levels(item_codes: list[str], warehouse: str) -> dict[str, float]:
	rows = frappe.get_all(
		"Bin",
		filters={"item_code": ("in", item_codes), "warehouse": warehouse},
		fields=["item_code", "actual_qty"],
	)
	return {row.item_code: flt(row.actual_qty) for row in rows}


def set_stock_levels(page, target_quantities: dict[str, float]) -> None:
	"""Move the stock of each size of one product page to its target in the Ecommerce Warehouse.
	Increases go through the page's own Material Receipt. Decreases go out as one Material Issue."""
	warehouse = frappe.get_cached_value("Commera Settings", "Commera Settings", "ecommerce_warehouse")
	if not warehouse:
		frappe.throw(_("Set the Ecommerce Warehouse in Commera Settings before importing stock."))

	current = get_stock_levels(list(target_quantities), warehouse)
	increases = {}
	decreases = {}
	for item_code, target in target_quantities.items():
		difference = max(flt(target), 0) - current.get(item_code, 0)
		if difference > 0:
			increases[item_code] = difference
		elif difference < 0:
			decreases[item_code] = -difference

	if increases:
		page.receive_stock(increases)
	if decreases:
		issue_stock(decreases, warehouse)


def issue_stock(quantities: dict[str, float], warehouse: str) -> str:
	stock_entry = frappe.new_doc("Stock Entry")
	stock_entry.stock_entry_type = "Material Issue"
	stock_entry.company = frappe.get_cached_value("Warehouse", warehouse, "company")
	for item_code, quantity in quantities.items():
		stock_entry.append("items", {"item_code": item_code, "qty": quantity, "s_warehouse": warehouse})
	stock_entry.insert()
	stock_entry.submit()
	return stock_entry.name
